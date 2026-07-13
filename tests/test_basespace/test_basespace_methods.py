import pytest
import requests
from unittest.mock import MagicMock

from bioforklift.basespace import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    DownloadedFileItem,
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
        ds_a = DatasetItem.model_validate({"Id": "ds.a", "Name": "sampleA"})

        with pytest.raises(BaseSpaceDatasetError, match="No dataset match"):
            mock_methods.filter_datasets(["sampleC"], [ds_a])

    def test_filter_datasets_ambiguous_raises(self, mock_methods):
        ds_a = DatasetItem.model_validate({"Id": "ds.a", "Name": "sampleA"})
        ds_a2 = DatasetItem.model_validate({"Id": "ds.a2", "Name": "sampleA"})

        with pytest.raises(BaseSpaceDatasetError, match="Multiple datasets"):
            mock_methods.filter_datasets(["sampleA"], [ds_a, ds_a2])

    def test_filter_datasets_duplicate_sample_names_raises(self, mock_methods):
        # A duplicated sample name must be rejected before any matching happens.
        ds_a = DatasetItem.model_validate({"Id": "ds.a", "Name": "sampleA"})

        with pytest.raises(BaseSpaceDatasetError, match="Duplicate sample name"):
            mock_methods.filter_datasets(["sampleA", "sampleA"], [ds_a])


class TestDownloadDatasetFiles:
    def test_download_dataset_files_dry_run(self, mock_methods, tmp_path):
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_L001_R1_001.fastq.gz", "HrefContent": "https://x/1"}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "Sample_L001_R2_001.fastq.gz", "HrefContent": "https://x/2"}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))
        mock_fc = mock_methods.endpoints.files_content = MagicMock()

        result = mock_methods.download_dataset_files([item], dest_dir=tmp_path, dry_run=True)

        mock_fc.assert_not_called()
        # Returns a dict of sample name -> its files, each with a resolved local path.
        assert list(result.keys()) == ["Sample"]
        assert [file.name for file in result["Sample"]] == [
            "Sample_L001_R1_001.fastq.gz",
            "Sample_L001_R2_001.fastq.gz",
        ]
        assert result["Sample"][0].local_path == tmp_path / "Sample_L001_R1_001.fastq.gz"
        # Nothing is actually written during a dry run.
        assert not (tmp_path / "Sample_L001_R1_001.fastq.gz").exists()

    def test_download_interrupted_stream_leaves_no_partial_file(self, mock_methods, tmp_path):
        # A stream that drops mid-download must not leave a truncated file at the final
        # path, nor a leftover temp/.part file in the destination directory.
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_S1_L001_R1_001.fastq.gz"}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "Sample_S1_L001_R2_001.fastq.gz"}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))

        def broken_stream(chunk_size=None):
            yield b"PARTIAL"
            raise requests.ConnectionError("stream dropped mid-download")

        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_response = mock_fc.return_value.__enter__.return_value
        mock_response.iter_content.side_effect = broken_stream

        with pytest.raises(requests.ConnectionError):
            mock_methods.download_dataset_files([item], dest_dir=tmp_path)

        # No file at the final destination and no partial temp file left behind.
        assert not (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").exists()
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize("file_count", [1, 3, 0])
    def test_paired_end_with_bad_file_count_raises(self, mock_methods, tmp_path, file_count):
        files = [
            DatasetFileItem.model_validate({"Id": str(i), "Name": f"Sample_L001_R{i}_001.fastq.gz", "HrefContent": f"https://x/{i}"})
            for i in range(file_count)
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))

        with pytest.raises(BaseSpaceMissingReadError):
            mock_methods.download_dataset_files([item], dest_dir=tmp_path)

    def test_paired_end_with_unbalanced_reads_raises(self, mock_methods, tmp_path):
        # Even file count (2) but both files are R1 with no R2 -> must still raise.
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "SampleA_S1_L001_R1_001.fastq.gz", "HrefContent": "https://x/1"}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "SampleB_S1_L002_R1_001.fastq.gz", "HrefContent": "https://x/2"}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))

        with pytest.raises(BaseSpaceMissingReadError, match="not balanced"):
            mock_methods.download_dataset_files([item], dest_dir=tmp_path)

    def test_paired_end_with_extra_non_read_file_raises(self, mock_methods, tmp_path):
        # A balanced R1/R2 pair plus an unexpected non-R1/R2 file (e.g. an index read)
        # must raise: every file has to be accounted for as an R1 or R2 read.
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_S1_L001_R1_001.fastq.gz"}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "Sample_S1_L001_R2_001.fastq.gz"}),
            DatasetFileItem.model_validate({"Id": "3", "Name": "Sample_S1_L001_X1_001.fastq.gz"}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))

        with pytest.raises(BaseSpaceMissingReadError, match="Every file must be an R1 or R2 read"):
            mock_methods.download_dataset_files([item], dest_dir=tmp_path)

    def test_paired_end_balanced_downloads_both_reads(self, mock_methods, tmp_path):
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_S1_L001_R1_001.fastq.gz", "HrefContent": "https://x/1"}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "Sample_S1_L001_R2_001.fastq.gz", "HrefContent": "https://x/2"}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_response = mock_fc.return_value.__enter__.return_value
        mock_response.iter_content.return_value = [b"DATA"]

        result = mock_methods.download_dataset_files([item], dest_dir=tmp_path)

        assert list(result.keys()) == ["Sample"]
        assert len(result["Sample"]) == 2
        assert (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").read_bytes() == b"DATA"
        assert (tmp_path / "Sample_S1_L001_R2_001.fastq.gz").read_bytes() == b"DATA"

    def test_download_size_mismatch_raises(self, mock_methods, tmp_path):
        # A completed-but-short body (bytes written != Size) must raise and leave
        # nothing behind (no final file, no temp).
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_S1_L001_R1_001.fastq.gz", "Size": 10}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "Sample_S1_L001_R2_001.fastq.gz", "Size": 10}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_response = mock_fc.return_value.__enter__.return_value
        mock_response.iter_content.return_value = [b"SHORT"]  # 5 bytes != Size of 10

        with pytest.raises(BaseSpaceDownloadError, match="Incomplete download"):
            mock_methods.download_dataset_files([item], dest_dir=tmp_path)

        assert list(tmp_path.iterdir()) == []

    def test_download_size_match_succeeds(self, mock_methods, tmp_path):
        # Bytes written across chunks equal Size -> the file is written.
        files = [
            DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_S1_L001_R1_001.fastq.gz", "Size": 4}),
            DatasetFileItem.model_validate({"Id": "2", "Name": "Sample_S1_L001_R2_001.fastq.gz", "Size": 4}),
        ]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_response = mock_fc.return_value.__enter__.return_value
        mock_response.iter_content.return_value = [b"DA", b"TA"]  # 4 bytes total == Size

        result = mock_methods.download_dataset_files([item], dest_dir=tmp_path)

        assert len(result["Sample"]) == 2
        assert (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").read_bytes() == b"DATA"
        assert (tmp_path / "Sample_S1_L001_R2_001.fastq.gz").stat().st_size == 4


class TestValidatePairedEnd:
    def test_balanced_returns_true(self, mock_methods, tmp_path):
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        files = [
            DownloadedFileItem(id="1", name="Sample_S1_L001_R1_001.fastq.gz", local_path=tmp_path / "Sample_S1_L001_R1_001.fastq.gz"),
            DownloadedFileItem(id="2", name="Sample_S1_L001_R2_001.fastq.gz", local_path=tmp_path / "Sample_S1_L001_R2_001.fastq.gz"),
        ]

        assert mock_methods._validate_paired_end(item, files) is True

    def test_not_paired_end_raises(self, mock_methods, tmp_path):
        # A dataset without IsPairedEnd (false or missing) is rejected: paired-end only.
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": False}}}
        )
        files = [
            DownloadedFileItem(id="1", name="Sample_S1_L001_R1_001.fastq.gz", local_path=tmp_path / "Sample_S1_L001_R1_001.fastq.gz"),
        ]

        with pytest.raises(BaseSpaceMissingReadError, match="only paired-end datasets are supported"):
            mock_methods._validate_paired_end(item, files)

    def test_download_validate_false_skips_check(self, mock_methods, tmp_path):
        # With validate=False, an unbalanced set (R1 only) is downloaded without raising.
        files = [DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_S1_L001_R1_001.fastq.gz"})]
        item = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "Sample", "Attributes": {"common_fastq": {"IsPairedEnd": True}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"DATA"]

        result = mock_methods.download_dataset_files([item], dest_dir=tmp_path, validate=False)

        assert list(result.keys()) == ["Sample"]
        assert (tmp_path / "Sample_S1_L001_R1_001.fastq.gz").read_bytes() == b"DATA"


class TestConcatenateReadSets:
    def test_concatenates_lanes_in_order(self, mock_methods, tmp_path):
        # Two lanes per read; output must be lane-ordered (L001 then L002) regardless of
        # the order the files are passed in.
        r1_l2 = DownloadedFileItem(id="1", name="Sample_S1_L002_R1_001.fastq.gz", size=2, local_path=tmp_path / "Sample_S1_L002_R1_001.fastq.gz")
        r1_l1 = DownloadedFileItem(id="2", name="Sample_S1_L001_R1_001.fastq.gz", size=2, local_path=tmp_path / "Sample_S1_L001_R1_001.fastq.gz")
        r2_l1 = DownloadedFileItem(id="3", name="Sample_S1_L001_R2_001.fastq.gz", size=2, local_path=tmp_path / "Sample_S1_L001_R2_001.fastq.gz")
        r2_l2 = DownloadedFileItem(id="4", name="Sample_S1_L002_R2_001.fastq.gz", size=2, local_path=tmp_path / "Sample_S1_L002_R2_001.fastq.gz")
        for file_item, data in [(r1_l2, b"22"), (r1_l1, b"11"), (r2_l1, b"aa"), (r2_l2, b"bb")]:
            file_item.local_path.write_bytes(data)

        # Deliberately unordered input.
        read_sets = {"Sample": [r1_l2, r1_l1, r2_l1, r2_l2]}

        outputs = mock_methods.concatenate_read_sets(read_sets)

        assert (tmp_path / "Sample_R1.fastq.gz").read_bytes() == b"1122"
        assert (tmp_path / "Sample_R2.fastq.gz").read_bytes() == b"aabb"
        assert outputs == [
            ("Sample_R1.fastq.gz", tmp_path / "Sample_R1.fastq.gz"),
            ("Sample_R2.fastq.gz", tmp_path / "Sample_R2.fastq.gz"),
        ]

    def test_dry_run_writes_nothing(self, mock_methods, tmp_path):
        r1 = DownloadedFileItem(id="1", name="Sample_S1_L001_R1_001.fastq.gz", local_path=tmp_path / "Sample_S1_L001_R1_001.fastq.gz")
        r2 = DownloadedFileItem(id="2", name="Sample_S1_L001_R2_001.fastq.gz", local_path=tmp_path / "Sample_S1_L001_R2_001.fastq.gz")

        outputs = mock_methods.concatenate_read_sets({"Sample": [r1, r2]}, dry_run=True)

        assert outputs == [
            ("Sample_R1.fastq.gz", tmp_path / "Sample_R1.fastq.gz"),
            ("Sample_R2.fastq.gz", tmp_path / "Sample_R2.fastq.gz"),
        ]
        assert list(tmp_path.iterdir()) == []

    def test_size_mismatch_raises_and_cleans_up(self, mock_methods, tmp_path):
        # Source is 2 bytes on disk but the API Size says 99 -> mismatch must raise and
        # leave no output or temp file behind (only the source files remain).
        r1 = DownloadedFileItem(id="1", name="Sample_S1_L001_R1_001.fastq.gz", size=99, local_path=tmp_path / "Sample_S1_L001_R1_001.fastq.gz")
        r2 = DownloadedFileItem(id="2", name="Sample_S1_L001_R2_001.fastq.gz", size=99, local_path=tmp_path / "Sample_S1_L001_R2_001.fastq.gz")
        for file_item in (r1, r2):
            file_item.local_path.write_bytes(b"XX")  # 2 bytes != 99

        with pytest.raises(BaseSpaceDownloadError, match="Concatenated size mismatch"):
            mock_methods.concatenate_read_sets({"Sample": [r1, r2]})

        assert not (tmp_path / "Sample_R1.fastq.gz").exists()
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "Sample_S1_L001_R1_001.fastq.gz",
            "Sample_S1_L001_R2_001.fastq.gz",
        ]


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

    def test_fetch_sample_fastqs_runs_pipeline_in_order(self, mock_methods, tmp_path):
        # The orchestrator must chain resolve -> list -> filter -> download -> concatenate,
        # threading each step's output into the next and returning the concatenation result.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        ds_item = DatasetItem.model_validate({"Id": "ds.1", "Name": "SampleA"})
        downloaded = {"SampleA": []}
        expected = [("SampleA_R1.fastq.gz", tmp_path / "SampleA_R1.fastq.gz")]

        mock_methods.resolve_collection_id = MagicMock(return_value=search_item)
        mock_methods.list_datasets = MagicMock(return_value=[ds_item])
        mock_methods.filter_datasets = MagicMock(return_value=[ds_item])
        mock_methods.download_dataset_files = MagicMock(return_value=downloaded)
        mock_methods.concatenate_read_sets = MagicMock(return_value=expected)

        result = mock_methods.fetch_sample_fastqs(
            "collA", ["SampleA"], dest_dir=tmp_path, dry_run=True
        )

        assert result is expected
        mock_methods.resolve_collection_id.assert_called_once_with("collA")
        mock_methods.list_datasets.assert_called_once_with(search_item, dataset_types="common.fastq")
        mock_methods.filter_datasets.assert_called_once_with(["SampleA"], [ds_item])
        mock_methods.download_dataset_files.assert_called_once_with(
            [ds_item], dest_dir=tmp_path, dry_run=True, validate=True
        )
        mock_methods.concatenate_read_sets.assert_called_once_with(downloaded, dry_run=True)

    def test_fetch_sample_fastqs_no_concatenate_returns_lane_files(self, mock_methods, tmp_path):
        # concatenate=False returns the individual per-lane files as (name, path) tuples
        # and never calls the concatenation step.
        search_item = RunItem.model_validate({"Type": "run", "Run": {"Id": "run-1"}})
        ds_item = DatasetItem.model_validate({"Id": "ds.1", "Name": "SampleA"})
        lane_file = DownloadedFileItem(id="1", name="SampleA_L001_R1_001.fastq.gz", local_path=tmp_path / "SampleA_L001_R1_001.fastq.gz")

        mock_methods.resolve_collection_id = MagicMock(return_value=search_item)
        mock_methods.list_datasets = MagicMock(return_value=[ds_item])
        mock_methods.filter_datasets = MagicMock(return_value=[ds_item])
        mock_methods.download_dataset_files = MagicMock(return_value={"SampleA": [lane_file]})
        mock_methods.concatenate_read_sets = MagicMock()

        result = mock_methods.fetch_sample_fastqs(
            "collA", ["SampleA"], dest_dir=tmp_path, concatenate=False
        )

        assert result == [
            ("SampleA_L001_R1_001.fastq.gz", tmp_path / "SampleA_L001_R1_001.fastq.gz")
        ]
        mock_methods.concatenate_read_sets.assert_not_called()
