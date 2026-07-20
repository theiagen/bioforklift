from unittest.mock import MagicMock

import pytest
import requests

from bioforklift.basespace import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    StagedDatasetFile,
    OtherItem,
    ProjectItem,
    RunItem,
)
from bioforklift.basespace.basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
    BaseSpaceDownloadError,
    BaseSpaceMissingReadError,
)


def make_response(items, total_count):
    """A BaseSpaceResponse page wrapping the given items and total count."""
    return BaseSpaceResponse.model_validate(
        {
            "items": items,
            "paging": {"DisplayedCount": len(items), "TotalCount": total_count},
        }
    )


def make_dataset(ds_id, name, type_id="common.fastq", conforms_to=("common.files",), paired_end=None):
    """A DatasetItem carrying a DatasetType (and optional paired-end attribute)."""
    payload = {
        "Id": ds_id,
        "Name": name,
        "DatasetType": {"Id": type_id, "ConformsToIds": list(conforms_to)},
    }
    if paired_end is not None:
        payload["Attributes"] = {"common_fastq": {"IsPairedEnd": paired_end}}
    return DatasetItem.model_validate(payload)


def make_file(file_id, name, size=None):
    """A DatasetFileItem as returned by /datasets/{id}/files."""
    return DatasetFileItem.model_validate({"Id": file_id, "Name": name, "Size": size})


def make_staged(name, files, paired_end=True):
    """A StagedDatasetFile built without running validators (for download/concat tests)."""
    item = make_dataset(f"ds.{name}", name, paired_end=paired_end)
    return StagedDatasetFile.model_construct(dataset_item=item, dataset_file_items=list(files))


class TestFetchAllItems:
    def test_fetch_all_items_single_page(self, mock_methods):
        # The endpoint returns all items in a single page, so only one call is made.
        endpoint = MagicMock(side_effect=[make_response([0, 1], total_count=2)])

        result = mock_methods._fetch_all_items(endpoint)

        assert result == [0, 1]
        assert endpoint.call_count == 1
        paging_1 = endpoint.call_args_list[0].kwargs["paging"]
        assert paging_1.offset == 0
        assert paging_1.limit == 1000

    def test_fetch_all_items_multiple_pages(self, mock_methods):
        pages = [
            make_response(list(range(0, 1000)), total_count=2500),
            make_response(list(range(1000, 2000)), total_count=2500),
            make_response(list(range(2000, 2500)), total_count=2500),
        ]
        endpoint = MagicMock(side_effect=pages)

        result = mock_methods._fetch_all_items(endpoint)

        assert len(result) == 2500
        assert endpoint.call_count == 3
        offsets = [call.kwargs["paging"].offset for call in endpoint.call_args_list]

        # offset and limit are hardcoded in _fetch_all_items, so we can assert the expected values.
        assert offsets == [0, 1000, 2000]
        assert all(call.kwargs["paging"].limit == 1000 for call in endpoint.call_args_list)

    def test_fetch_all_items_empty_first_page(self, mock_methods):
        endpoint = MagicMock(side_effect=[make_response([], total_count=0)])

        result = mock_methods._fetch_all_items(endpoint)

        assert result == []
        assert endpoint.call_count == 1


class TestResolveCollectionId:
    @pytest.mark.parametrize(
        "collection_id, items, expected_id",
        [
            ("run-1", [RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})], "run-1"),
            ("MyRun", [RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1", "Name": "MyRun"}})], "run-1"),
            ("proj-1", [ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1"}})], "proj-1"),
            ("MyProject", [ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1", "Name": "MyProject"}})], "proj-1"),
            ("dedup", [RunItem.model_validate({"Type": "run", "Run": {"Id": "dedup", "Name": "dedup"}})], "dedup"),
        ],
    )
    def test_resolve_collection_id_unique_match(self, mock_methods, collection_id, items, expected_id):
        search_mock = mock_methods.endpoints.search = MagicMock(
            return_value=make_response(items, total_count=len(items))
        )

        result = mock_methods.resolve_collection_id(collection_id)

        assert result.id == expected_id

        # Every (scope, field) pair is searched with a PascalCase Lucene clause for this collection_id.
        clauses = [(call.kwargs["scope"], call.kwargs["query"]) for call in search_mock.call_args_list]
        assert clauses == [
            ("runs", f'Id:"{collection_id}"'),
            ("runs", f'Name:"{collection_id}"'),
            ("runs", f'ExperimentName:"{collection_id}"'),
            ("projects", f'Id:"{collection_id}"'),
            ("projects", f'Name:"{collection_id}"'),
        ]

    @pytest.mark.parametrize(
        "collection_id, items, error_match",
        [
            # nothing matches
            ("none", [RunItem.model_validate({"Type": "run", "Run": {"Id": "other"}})], "no project or run exactly matches"),
            # close but inexact match is filtered out
            ("ABC", [RunItem.model_validate({"Type": "run", "Run": {"Id": "ABCD"}})], "no project or run exactly matches"),
            # an OtherItem (no id/name) is skipped
            ("unknown", [OtherItem.model_validate({"Type": "sample", "Foo": "bar"})], "no project or run exactly matches"),
            # two distinct items both match
            (
                "dup",
                [
                    RunItem.model_validate({"Type": "run", "Run": {"Id": "dup"}}),
                    ProjectItem.model_validate({"Type": "project", "Project": {"Id": "dup"}}),
                ],
                "ambiguous",
            ),
        ],
    )
    def test_resolve_collection_id_bad_match_raises(self, mock_methods, collection_id, items, error_match):
        mock_methods.endpoints.search = MagicMock(return_value=make_response(items, total_count=len(items)))

        with pytest.raises(BaseSpaceCollectionIdError, match=error_match):
            mock_methods.resolve_collection_id(collection_id)


class TestFilterDatasets:
    def test_filter_datasets_unmatched_raises(self, mock_methods):
        ds_a = make_dataset("ds.a", "sampleA")

        with pytest.raises(BaseSpaceDatasetError, match="No dataset match"):
            mock_methods.filter_datasets(["sampleC"], [ds_a])

    def test_filter_datasets_ambiguous_raises(self, mock_methods):
        ds_a = make_dataset("ds.a", "sampleA")
        ds_a2 = make_dataset("ds.a2", "sampleA")

        with pytest.raises(BaseSpaceDatasetError, match="Multiple datasets"):
            mock_methods.filter_datasets(["sampleA"], [ds_a, ds_a2])

    def test_filter_datasets_duplicate_sample_names_raises(self, mock_methods):
        # A duplicated sample name must be rejected before any matching happens.
        ds_a = make_dataset("ds.a", "sampleA")

        with pytest.raises(BaseSpaceDatasetError, match="Duplicate sample name"):
            mock_methods.filter_datasets(["sampleA", "sampleA"], [ds_a])

    def test_filter_datasets_matches_conforming_type(self, mock_methods):
        # A dataset whose Id is a typed variant (illumina.fastq.v1.8) but which conforms to
        # common.fastq must still be matched under the default filter.
        ds_a = make_dataset(
            "ds.a", "sampleA", type_id="illumina.fastq.v1.8",
            conforms_to=("common.files", "common.fastq"),
        )

        result = mock_methods.filter_datasets(["sampleA"], [ds_a])

        assert result == [ds_a]

    def test_filter_datasets_drops_non_matching_type(self, mock_methods):
        # A dataset of an unrelated type is dropped, leaving the requested sample unmatched.
        ds_a = make_dataset("ds.a", "sampleA", type_id="common.bam", conforms_to=("common.files",))

        with pytest.raises(BaseSpaceDatasetError, match="No dataset match"):
            mock_methods.filter_datasets(["sampleA"], [ds_a])

    def test_filter_datasets_same_name_across_types_resolves_to_matching(self, mock_methods):
        # Two datasets share a Name but differ in type; narrowing by type first must
        # resolve to the single common.fastq dataset instead of raising "Multiple datasets".
        ds_fastq = make_dataset("ds.a", "sampleA", type_id="common.fastq")
        ds_bam = make_dataset("ds.a.bam", "sampleA", type_id="common.bam", conforms_to=("common.files",))

        result = mock_methods.filter_datasets(["sampleA"], [ds_bam, ds_fastq])

        assert result == [ds_fastq]

    def test_filter_datasets_none_type_keeps_all_types(self, mock_methods):
        # dataset_types=None disables the type filter, so a non-fastq dataset still matches.
        ds_bam = make_dataset("ds.a", "sampleA", type_id="common.bam", conforms_to=("common.files",))

        result = mock_methods.filter_datasets(["sampleA"], [ds_bam], dataset_types=None)

        assert result == [ds_bam]


class TestPrepareDatasetFiles:
    def _mock_files(self, mock_methods, files):
        mock_methods.endpoints.datasets_files = MagicMock(
            return_value=make_response(files, total_count=len(files))
        )

    def test_builds_staged_files(self, mock_methods):
        files = [
            make_file("1", "Sample_S1_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_S1_L001_R2_001.fastq.gz"),
        ]
        item = make_dataset("ds.1", "Sample", paired_end=True)
        self._mock_files(mock_methods, files)

        staged = mock_methods.prepare_dataset_files([item])

        assert len(staged) == 1
        assert isinstance(staged[0], StagedDatasetFile)
        assert [file.name for file in staged[0].dataset_file_items] == [
            "Sample_S1_L001_R1_001.fastq.gz",
            "Sample_S1_L001_R2_001.fastq.gz",
        ]

    def test_validation_is_wired_in(self, mock_methods):
        # prepare_dataset_files owns no validation logic; it just constructs StagedDatasetFile,
        # which runs the model validators. One invalid case (not paired-end) proves the wiring;
        # the full validation matrix lives in test_basespace_models.py::TestStagedDatasetFile.
        files = [
            make_file("1", "Sample_S1_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_S1_L001_R2_001.fastq.gz"),
        ]
        item = make_dataset("ds.1", "Sample", paired_end=False)
        self._mock_files(mock_methods, files)

        with pytest.raises(BaseSpaceMissingReadError, match="only paired-end datasets are supported"):
            mock_methods.prepare_dataset_files([item])

    def test_validate_false_skips_check(self, mock_methods):
        # With validate=False, an unbalanced set (R1 only) is staged without raising.
        files = [make_file("1", "Sample_S1_L001_R1_001.fastq.gz")]
        item = make_dataset("ds.1", "Sample", paired_end=False)
        self._mock_files(mock_methods, files)

        staged = mock_methods.prepare_dataset_files([item], validate=False)

        assert len(staged) == 1
        assert len(staged[0].dataset_file_items) == 1


class TestDownloadDatasetFiles:
    def test_dry_run_sets_paths_writes_nothing(self, mock_methods, tmp_path):
        files = [
            make_file("1", "Sample_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_L001_R2_001.fastq.gz"),
        ]
        staged = make_staged("Sample", files)
        mock_fc = mock_methods.endpoints.files_content = MagicMock()

        result = mock_methods.download_dataset_files([staged], dest_dir=tmp_path, dry_run=True)

        mock_fc.assert_not_called()
        # Returns the same staged files, each file's local path resolved under dest_dir.
        assert result == [staged]
        assert files[0]._local_path == tmp_path / "Sample_L001_R1_001.fastq.gz"
        # Nothing is actually written during a dry run.
        assert list(tmp_path.iterdir()) == []

    def test_interrupted_stream_leaves_no_partial_file(self, mock_methods, tmp_path):
        # A stream that drops mid-download must not leave a truncated file at the final
        # path, nor a leftover temp/.part file in the destination directory.
        files = [
            make_file("1", "Sample_S1_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_S1_L001_R2_001.fastq.gz"),
        ]
        staged = make_staged("Sample", files)

        def broken_stream(chunk_size=None):
            yield b"PARTIAL"
            raise requests.ConnectionError("stream dropped mid-download")

        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_response = mock_fc.return_value.__enter__.return_value
        mock_response.iter_content.side_effect = broken_stream

        with pytest.raises(requests.ConnectionError):
            mock_methods.download_dataset_files([staged], dest_dir=tmp_path)

        # No file at the final destination and no partial temp file left behind.
        assert not (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").exists()
        assert list(tmp_path.iterdir()) == []

    def test_size_mismatch_raises(self, mock_methods, tmp_path):
        # A completed-but-short body (bytes written != Size) must raise and leave nothing behind.
        files = [make_file("1", "Sample_S1_L001_R1_001.fastq.gz", size=10)]
        staged = make_staged("Sample", files)
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"SHORT"]  # 5 bytes != 10

        with pytest.raises(BaseSpaceDownloadError, match="Incomplete download"):
            mock_methods.download_dataset_files([staged], dest_dir=tmp_path)

        assert list(tmp_path.iterdir()) == []

    def test_balanced_downloads_both_reads(self, mock_methods, tmp_path):
        files = [
            make_file("1", "Sample_S1_L001_R1_001.fastq.gz"),
            make_file("2", "Sample_S1_L001_R2_001.fastq.gz"),
        ]
        staged = make_staged("Sample", files)
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"DATA"]

        mock_methods.download_dataset_files([staged], dest_dir=tmp_path)

        assert (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").read_bytes() == b"DATA"
        assert (tmp_path / "Sample_S1_L001_R2_001.fastq.gz").read_bytes() == b"DATA"

    def test_size_match_succeeds(self, mock_methods, tmp_path):
        # Bytes written across chunks equal Size -> the file is written.
        files = [make_file("1", "Sample_S1_L001_R1_001.fastq.gz", size=4)]
        staged = make_staged("Sample", files)
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"DA", b"TA"]  # 4 bytes total == Size

        mock_methods.download_dataset_files([staged], dest_dir=tmp_path)

        assert (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").stat().st_size == 4


class TestConcatenateReadSets:
    def _staged(self, name, specs, tmp_path):
        # specs: list of (filename, data_or_None, size).
        files = []
        for fname, data, size in specs:
            file_item = make_file(fname, fname, size=size)
            file_item._local_path = tmp_path / fname
            if data is not None:
                file_item._local_path.write_bytes(data)
            files.append(file_item)
        return make_staged(name, files)

    def test_concatenates_lanes_in_order(self, mock_methods, tmp_path):
        # Two lanes per read; output must be lane-ordered (L001 then L002) regardless of
        # the order the files are passed in.
        staged = self._staged(
            "Sample",
            [
                ("Sample_S1_L002_R1_001.fastq.gz", b"22", 2),
                ("Sample_S1_L001_R1_001.fastq.gz", b"11", 2),
                ("Sample_S1_L001_R2_001.fastq.gz", b"aa", 2),
                ("Sample_S1_L002_R2_001.fastq.gz", b"bb", 2),
            ],
            tmp_path,
        )

        mock_methods.concatenate_read_sets([staged])

        assert (tmp_path / "Sample_R1.fastq.gz").read_bytes() == b"1122"
        assert (tmp_path / "Sample_R2.fastq.gz").read_bytes() == b"aabb"

    def test_dry_run_writes_nothing(self, mock_methods, tmp_path):
        staged = self._staged(
            "Sample",
            [
                ("Sample_S1_L001_R1_001.fastq.gz", None, None),
                ("Sample_S1_L001_R2_001.fastq.gz", None, None),
            ],
            tmp_path,
        )

        mock_methods.concatenate_read_sets([staged], dry_run=True)

        assert list(tmp_path.iterdir()) == []

    def test_size_mismatch_raises_and_cleans_up(self, mock_methods, tmp_path):
        # Source is 2 bytes on disk but the API Size says 99 -> mismatch must raise and
        # leave no output or temp file behind (only the source files remain).
        staged = self._staged(
            "Sample",
            [
                ("Sample_S1_L001_R1_001.fastq.gz", b"XX", 99),
                ("Sample_S1_L001_R2_001.fastq.gz", b"XX", 99),
            ],
            tmp_path,
        )

        with pytest.raises(BaseSpaceDownloadError, match="Concatenated size mismatch"):
            mock_methods.concatenate_read_sets([staged])

        assert not (tmp_path / "Sample_R1.fastq.gz").exists()
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "Sample_S1_L001_R1_001.fastq.gz",
            "Sample_S1_L001_R2_001.fastq.gz",
        ]

    def test_no_lane_files_are_skipped(self, mock_methods, tmp_path, caplog):
        # Valid R1/R2 reads with no _L### token can't be ordered, so nothing is concatenated.
        staged = self._staged(
            "NL",
            [
                ("NL_R1.fastq.gz", b"AA", None),
                ("NL_R2.fastq.gz", b"BB", None),
            ],
            tmp_path,
        )

        with caplog.at_level("WARNING"):
            mock_methods.concatenate_read_sets([staged])

        # Only the original source files remain; no new concatenated output written.
        assert sorted(p.name for p in tmp_path.iterdir()) == ["NL_R1.fastq.gz", "NL_R2.fastq.gz"]
        # The skip must be surfaced, not silent.
        assert "No laned FASTQ files found" in caplog.text


class TestListDatasets:
    def test_list_datasets_routes_project_scope(self, mock_methods):
        # A project item must scope the /datasets query by project_id (not input_runs).
        item = ProjectItem.model_validate({"Type": "project", "Project": {"Id": "proj-1"}})
        mock_methods._fetch_all_items = MagicMock(return_value=[])

        mock_methods.list_datasets(item)

        kwargs = mock_methods._fetch_all_items.call_args.kwargs
        assert kwargs["project_id"] == "proj-1"
        assert kwargs["input_runs"] is None

    def test_list_datasets_routes_run_scope(self, mock_methods):
        # A run item must scope the /datasets query by input_runs (not project_id).
        item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        mock_methods._fetch_all_items = MagicMock(return_value=[])

        mock_methods.list_datasets(item)

        kwargs = mock_methods._fetch_all_items.call_args.kwargs
        assert kwargs["input_runs"] == "run-1"
        assert kwargs["project_id"] is None

    def test_list_datasets_other_item_raises(self, mock_methods):
        # An OtherItem (e.g. a sample) cannot be used to scope the /datasets query (currently).
        item = OtherItem.model_validate({"Type": "sample", "Sample": {"Id": "sample-1"}})

        with pytest.raises(BaseSpaceCollectionIdError, match="Cannot list datasets for OtherItem"):
            mock_methods.list_datasets(item)


class TestFetchSampleFastqs:
    def test_fetch_sample_fastqs_empty_samples_raises(self, mock_methods):
        with pytest.raises(BaseSpaceDatasetError, match="No samples provided"):
            mock_methods.fetch_sample_fastqs("collA", [])

    def test_fetch_sample_fastqs_duplicate_samples_raises(self, mock_methods):
        # The duplicate guard must fire before the pipeline (resolve/list/etc.) is reached.
        mock_methods.resolve_collection_id = MagicMock()

        with pytest.raises(BaseSpaceDatasetError, match="Duplicate sample name"):
            mock_methods.fetch_sample_fastqs("collA", ["SampleA", "SampleA"])

    def _wire_pipeline(self, mock_methods, search_item, ds_item, staged):
        mock_methods.resolve_collection_id = MagicMock(return_value=search_item)
        mock_methods.list_datasets = MagicMock(return_value=[ds_item])
        mock_methods.filter_datasets = MagicMock(return_value=[ds_item])
        mock_methods.prepare_dataset_files = MagicMock(return_value=[staged])
        mock_methods.download_dataset_files = MagicMock(return_value=[staged])
        mock_methods.concatenate_read_sets = MagicMock()

    def test_fetch_sample_fastqs_runs_pipeline_in_order(self, mock_methods, tmp_path):
        # The orchestrator must chain resolve -> list -> filter -> prepare -> download -> concatenate,
        # threading each step's output into the next.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        ds_item = DatasetItem.model_validate({"Id": "ds.1", "Name": "SampleA"})
        staged = StagedDatasetFile.model_construct(dataset_item=ds_item, dataset_file_items=[])
        self._wire_pipeline(mock_methods, search_item, ds_item, staged)

        result = mock_methods.fetch_sample_fastqs(
            "collA", ["SampleA"], dest_dir=tmp_path, dry_run=True, concatenate=True
        )

        assert result is None
        mock_methods.resolve_collection_id.assert_called_once_with("collA")
        mock_methods.list_datasets.assert_called_once_with(search_item)
        mock_methods.filter_datasets.assert_called_once_with(
            samples=["SampleA"], ds_items=[ds_item], dataset_types=["common.fastq"]
        )
        mock_methods.prepare_dataset_files.assert_called_once_with(ds_items=[ds_item], validate=True)
        mock_methods.download_dataset_files.assert_called_once_with(
            staged_dataset_files=[staged], dest_dir=tmp_path, dry_run=True, progress=True
        )
        mock_methods.concatenate_read_sets.assert_called_once_with(
            staged_dataset_files=[staged], dry_run=True
        )

    def test_fetch_sample_fastqs_default_skips_concatenate(self, mock_methods, tmp_path):
        # concatenate defaults to False, so the concatenation step is never called.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        ds_item = DatasetItem.model_validate({"Id": "ds.1", "Name": "SampleA"})
        staged = StagedDatasetFile.model_construct(dataset_item=ds_item, dataset_file_items=[])
        self._wire_pipeline(mock_methods, search_item, ds_item, staged)

        result = mock_methods.fetch_sample_fastqs("collA", ["SampleA"], dest_dir=tmp_path)

        assert result is None
        mock_methods.concatenate_read_sets.assert_not_called()
