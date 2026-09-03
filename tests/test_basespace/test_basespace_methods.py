from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from bioforklift.basespace import (
    OtherItem,
    ProjectItem,
    RunItem,
)
from bioforklift.basespace.basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
    BaseSpaceDownloadError,
)


class TestResolveCollectionId:
    def test_searches_every_scope(self, mock_methods, make_response):
        # Only a run matches, but projects is still searched
        run = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "MyRun"}})
        search_mock = mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response([run], total_count=1),
                make_response([], total_count=0),
            ]
        )

        result = mock_methods.resolve_collection_id("MyRun")

        assert result == run

        clauses = [(call.kwargs["scope"], call.kwargs["query"]) for call in search_mock.call_args_list]
        assert clauses == [
            ("runs", 'ExperimentName:"MyRun"'),
            ("projects", 'Name:"MyRun"'),
        ]

    def test_project_match_after_run_miss(self, mock_methods, make_response):
        # No run matches, so the projects scope is searched next and resolves the name.
        project = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "MyProject"}})
        search_mock = mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response([], total_count=0),
                make_response([project], total_count=1),
            ]
        )

        result = mock_methods.resolve_collection_id("MyProject")

        assert result == project

        clauses = [(call.kwargs["scope"], call.kwargs["query"]) for call in search_mock.call_args_list]
        assert clauses == [
            ("runs", 'ExperimentName:"MyProject"'),
            ("projects", 'Name:"MyProject"'),
        ]

    def test_match_in_both_scopes_without_priority_raises(self, mock_methods, make_response):
        # A run and a project share the name; with no priority there is nothing to break the tie.
        run = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "Shared"}})
        project = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "Shared"}})
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response([run], total_count=1),
                make_response([project], total_count=1),
            ]
        )

        with pytest.raises(BaseSpaceCollectionIdError, match="matched in more than one scope"):
            mock_methods.resolve_collection_id("Shared")

    @pytest.mark.parametrize("priority, expected_id", [("runs", "run-1"), ("projects", "proj-1")])
    def test_priority_picks_scope(self, mock_methods, make_response, priority, expected_id):
        # Both scopes resolve to exactly one item, so `priority` decides which is returned.
        run = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "Shared"}})
        project = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "Shared"}})
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response([run], total_count=1),
                make_response([project], total_count=1),
            ]
        )

        result = mock_methods.resolve_collection_id("Shared", priority=priority)

        assert result.id == expected_id

    def test_priority_falls_back_to_other_scope(self, mock_methods, make_response):
        # The prioritized scope has no exact match at all, so the other scope resolves the name.
        project = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "Shared"}})
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response([], total_count=0),
                make_response([project], total_count=1),
            ]
        )

        result = mock_methods.resolve_collection_id("Shared", priority="runs")

        assert result == project

    def test_ambiguous_priority_scope_raises(self, mock_methods, make_response):
        # `runs` is prioritized and matches twice, which can't be narrowed. The single project
        # match is never considered: a prioritized scope that matched has no fallback.
        runs = [
            RunItem.model_validate({"Type": "run", "Run": {"Id": f"run-{index}", "ExperimentName": "Shared"}})
            for index in (1, 2)
        ]
        project = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "Shared"}})
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response(runs, total_count=len(runs)),
                make_response([project], total_count=1),
            ]
        )

        with pytest.raises(BaseSpaceCollectionIdError, match="matched 2 items in `runs`"):
            mock_methods.resolve_collection_id("Shared", priority="runs")

    def test_duplicates_outside_resolved_scope_are_ignored(self, mock_methods, make_response):
        # The prioritized scope matches exactly once, so duplicate project names never apply.
        run = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "Shared"}})
        projects = [
            ProjectItem.model_validate({"Type": "project", "Project": {"Id": f"proj-{index}", "Name": "Shared"}})
            for index in (1, 2)
        ]
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response([run], total_count=1),
                make_response(projects, total_count=len(projects)),
            ]
        )

        result = mock_methods.resolve_collection_id("Shared", priority="runs")

        assert result == run

    def test_every_scope_ambiguous_raises(self, mock_methods, make_response):
        # Nothing can be narrowed anywhere, and the error names the prioritized scope
        # regardless of how few matches the other scope had.
        runs = [
            RunItem.model_validate({"Type": "run", "Run": {"Id": f"run-{index}", "ExperimentName": "Shared"}})
            for index in (1, 2, 3)
        ]
        projects = [
            ProjectItem.model_validate({"Type": "project", "Project": {"Id": f"proj-{index}", "Name": "Shared"}})
            for index in (1, 2)
        ]
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response(runs, total_count=len(runs)),
                make_response(projects, total_count=len(projects)),
            ]
        )

        with pytest.raises(BaseSpaceCollectionIdError, match="matched 3 items in `runs`"):
            mock_methods.resolve_collection_id("Shared", priority="runs")

    def test_invalid_priority_raises(self, mock_methods):
        # `@validate_call` rejects an unknown scope before any search is issued.
        search_mock = mock_methods.endpoints.search = MagicMock()

        with pytest.raises(ValidationError):
            mock_methods.resolve_collection_id("Shared", priority="run")

        search_mock.assert_not_called()

    @pytest.mark.parametrize(
        "collection_id, run_items, project_items",
        [
            ("run-1", [RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "MyRun"}})], []),
            ("proj-1", [], [ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "MyProject"}})]),
            ("250612_M00123_0001", [RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "Name": "250612_M00123_0001"}})], []),
            ("MyRun", [RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "MyRun2"}})], []),
            ("unknown", [OtherItem.model_validate({"Type": "sample", "Foo": "bar"})], []),
            ("missing", [], []),
        ],
    )
    def test_bad_match_raises(self, mock_methods, make_response, collection_id, run_items, project_items):
        mock_methods.endpoints.search = MagicMock(
            side_effect=[
                make_response(run_items, total_count=len(run_items)),
                make_response(project_items, total_count=len(project_items)),
            ]
        )

        with pytest.raises(
            BaseSpaceCollectionIdError,
            match="no run experiment name or project name exactly matches",
        ):
            mock_methods.resolve_collection_id(collection_id)

    def test_multiple_exact_matches_in_scope_raises(self, mock_methods, make_response):
        # Two runs sharing one experiment name can't be narrowed to a single collection.
        items = [
            RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "ExperimentName": "Dup"}}),
            RunItem.model_validate({"Type": "run", "Run": {"Id": "run-2", "ExperimentName": "Dup"}}),
        ]
        mock_methods.endpoints.search = MagicMock(
            return_value=make_response(items, total_count=len(items))
        )

        with pytest.raises(BaseSpaceCollectionIdError, match="matched 2 items in `runs`"):
            mock_methods.resolve_collection_id("Dup")


class TestGetSearchItems:
    def test_forwards_scope_query_and_returns_items(self, mock_methods, make_response):
        items = [
            RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}}),
            ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1"}}),
        ]
        mock_methods.endpoints.search = MagicMock(
            return_value=make_response(items, total_count=len(items))
        )

        result = mock_methods.get_search_items(query='Name:"x"', scope="runs")

        assert result == items
        kwargs = mock_methods.endpoints.search.call_args.kwargs
        assert kwargs["scope"] == "runs"
        assert kwargs["query"] == 'Name:"x"'


class TestGetDatasets:
    def test_routes_project_scope(self, mock_methods, make_response):
        # A project item must scope the /datasets query by project_id (not input_runs).
        item = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1"}})
        mock_methods.endpoints.datasets = MagicMock(return_value=make_response([], total_count=0))

        mock_methods.get_datasets(item)

        kwargs = mock_methods.endpoints.datasets.call_args.kwargs
        assert kwargs["project_id"] == "proj-1"
        assert kwargs["input_runs"] is None

    def test_routes_run_scope(self, mock_methods, make_response):
        # A run item must scope the /datasets query by input_runs (not project_id).
        item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        mock_methods.endpoints.datasets = MagicMock(return_value=make_response([], total_count=0))

        mock_methods.get_datasets(item)

        kwargs = mock_methods.endpoints.datasets.call_args.kwargs
        assert kwargs["input_runs"] == "run-1"
        assert kwargs["project_id"] is None

    def test_other_item_raises(self, mock_methods):
        # An OtherItem (e.g. a sample) cannot be used to scope the /datasets query.
        item = OtherItem.model_validate({"Type": "sample", "Sample": {"Id": "sample-1"}})

        with pytest.raises(BaseSpaceCollectionIdError, match="Cannot list datasets for OtherItem"):
            mock_methods.get_datasets(item)


class TestGetDatasetFiles:
    def test_pages_files_for_dataset(self, mock_methods, make_response, make_dataset, make_file):
        files = [
            make_file("1", "Sample_S1_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_S1_L001_R2_001.fastq.gz"),
        ]
        ds_item = make_dataset("ds.1", "Sample", paired_end=True)
        mock_methods.endpoints.dataset_files = MagicMock(
            return_value=make_response(files, total_count=len(files))
        )

        result = mock_methods.get_dataset_files(ds_item)

        assert [file.name for file in result] == [
            "Sample_S1_L001_R1_001.fastq.gz",
            "Sample_S1_L001_R2_001.fastq.gz",
        ]
        # The dataset id is forwarded to the /datasets/{id}/files endpoint.
        assert mock_methods.endpoints.dataset_files.call_args.kwargs["dataset_id"] == "ds.1"


class TestDownloadDatasetFileContent:
    def test_dry_run_writes_nothing(self, mock_methods, make_file, tmp_path):
        ds_file = make_file("1", "Sample_L001_R1_001.fastq.gz")
        mock_fc = mock_methods.endpoints.file_content = MagicMock()

        result = mock_methods.download_dataset_file_content(ds_file, dest_dir=tmp_path, dry_run=True)

        mock_fc.assert_not_called()
        assert result is None
        assert list(tmp_path.iterdir()) == []

    def test_streams_to_dest_dir_under_original_name(self, mock_methods, make_file, tmp_path):
        ds_file = make_file("1", "Sample_L001_R1_001.fastq.gz", size=4)
        mock_fc = mock_methods.endpoints.file_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"DA", b"TA"]

        mock_methods.download_dataset_file_content(ds_file, dest_dir=tmp_path, progress=False)

        assert (tmp_path / "Sample_L001_R1_001.fastq.gz").read_bytes() == b"DATA"
        # Streamed via the file_content endpoint for this file id.
        assert mock_fc.call_args.kwargs["file_id"] == "1"

    def test_size_mismatch_raises(self, mock_methods, make_file, tmp_path):
        # download_dataset_file_content passes ds_file.size through as the expected size.
        ds_file = make_file("1", "Sample_L001_R1_001.fastq.gz", size=10)
        mock_fc = mock_methods.endpoints.file_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"SHORT"]  # 5 != 10

        with pytest.raises(BaseSpaceDownloadError, match="Incomplete download"):
            mock_methods.download_dataset_file_content(ds_file, dest_dir=tmp_path, progress=False)

        assert list(tmp_path.iterdir()) == []


class TestFetchSampleFastqs:
    def test_empty_samples_raises(self, mock_methods):
        with pytest.raises(BaseSpaceDatasetError, match="No samples provided"):
            mock_methods.fetch_sample_fastqs("collA", [])

    def test_duplicate_samples_raises(self, mock_methods):
        # The duplicate guard fires before any network call (resolve/list/etc.).
        with pytest.raises(BaseSpaceDatasetError, match="Duplicate sample name"):
            mock_methods.fetch_sample_fastqs("collA", ["SampleA", "SampleA"])

    def _wire_pipeline(self, mock_methods, monkeypatch, make_dataset, make_file, search_item):
        # Instance methods that hit the network are mocked on the object; the module-level
        # pure functions are monkeypatched in the basespace_methods namespace.
        ds_item = make_dataset("ds.1", "SampleA", paired_end=True)
        files = [
            make_file("1", "SampleA_L001_R1_001.fastq.gz"),
            make_file("2", "SampleA_L001_R2_001.fastq.gz"),
        ]
        mock_methods.resolve_collection_id = MagicMock(return_value=search_item)
        mock_methods.get_datasets = MagicMock(return_value=[ds_item])
        mock_methods.get_dataset_files = MagicMock(return_value=files)
        mock_methods.download_dataset_file_content = MagicMock()

        mock_filter = MagicMock(return_value=[ds_item])
        mock_match = MagicMock(return_value=[ds_item])
        mock_validate = MagicMock()
        mock_concat = MagicMock()
        monkeypatch.setattr("bioforklift.basespace.basespace_methods.filter_dataset_types", mock_filter)
        monkeypatch.setattr("bioforklift.basespace.basespace_methods.match_datasets_by_sample", mock_match)
        monkeypatch.setattr("bioforklift.basespace.basespace_methods.validate_paired_end_datasets", mock_validate)
        monkeypatch.setattr("bioforklift.basespace.basespace_methods.concatenate_dataset_files", mock_concat)
        return {
            "ds_item": ds_item,
            "files": files,
            "filter": mock_filter,
            "match": mock_match,
            "validate": mock_validate,
            "concat": mock_concat,
        }

    def test_runs_pipeline(self, mock_methods, tmp_path, monkeypatch, make_dataset, make_file):
        # Every stage is invoked once with the right args; downloads run per file.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        wiring = self._wire_pipeline(mock_methods, monkeypatch, make_dataset, make_file, search_item)

        result = mock_methods.fetch_sample_fastqs(
            "collA", ["SampleA"], dest_dir=tmp_path, dry_run=True, concatenate=True
        )

        assert result is None
        mock_methods.resolve_collection_id.assert_called_once_with("collA", priority=None)
        mock_methods.get_datasets.assert_called_once_with(search_item)
        wiring["filter"].assert_called_once_with([wiring["ds_item"]], ["common.fastq"])
        wiring["match"].assert_called_once_with(
            sample="SampleA", ds_items=[wiring["ds_item"]], group_by_lane=False
        )
        mock_methods.get_dataset_files.assert_called_once_with(wiring["ds_item"])
        wiring["validate"].assert_called_once_with(
            ds_items=[wiring["ds_item"]], ds_files=wiring["files"]
        )
        assert mock_methods.download_dataset_file_content.call_count == 2
        wiring["concat"].assert_called_once_with(
            samplename="SampleA",
            ds_files=wiring["files"],
            dest_dir=tmp_path,
            dry_run=True,
            validate_lane_naming=False,
            remove_sources=True,
        )

    def test_default_concatenates(self, mock_methods, tmp_path, monkeypatch, make_dataset, make_file):
        # concatenate defaults to True, so the concatenation step runs by default.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        wiring = self._wire_pipeline(mock_methods, monkeypatch, make_dataset, make_file, search_item)

        mock_methods.fetch_sample_fastqs("collA", ["SampleA"], dest_dir=tmp_path)

        wiring["concat"].assert_called_once_with(
            samplename="SampleA",
            ds_files=wiring["files"],
            dest_dir=tmp_path,
            dry_run=False,
            validate_lane_naming=False,
            remove_sources=True,
        )

    def test_no_concatenate_skips_concat(self, mock_methods, tmp_path, monkeypatch, make_dataset, make_file):
        # concatenate=False leaves the raw per-lane files (no concatenation step).
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        wiring = self._wire_pipeline(mock_methods, monkeypatch, make_dataset, make_file, search_item)

        mock_methods.fetch_sample_fastqs("collA", ["SampleA"], dest_dir=tmp_path, concatenate=False)

        wiring["concat"].assert_not_called()

    def test_remove_sources_forwarded(self, mock_methods, tmp_path, monkeypatch, make_dataset, make_file):
        # The opt-out reaches the concatenation step so per-lane files are kept.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        wiring = self._wire_pipeline(mock_methods, monkeypatch, make_dataset, make_file, search_item)

        mock_methods.fetch_sample_fastqs(
            "collA", ["SampleA"], dest_dir=tmp_path, remove_sources=False
        )

        assert wiring["concat"].call_args.kwargs["remove_sources"] is False
