import pytest
from unittest.mock import MagicMock

from bioforklift.basespace import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    ProjectItem,
    RunItem,
    UnknownItem,
)
from bioforklift.basespace.basespace_exceptions import (
    BaseSpaceCollectionIdError,
    BaseSpaceDatasetError,
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
        mock_methods.endpoints.search = MagicMock(return_value=make_response(items, total_count=len(items)))

        result = mock_methods.resolve_collection_id(collection_id)

        assert result.id == expected_id

    @pytest.mark.parametrize(
        "collection_id, items, error_match",
        [
            # nothing matches
            ("none", [RunItem.model_validate({"Type": "run", "Run": {"Id": "other"}})], "no project or run exactly matches"),
            # close but inexact match is filtered out
            ("ABC", [RunItem.model_validate({"Type": "run", "Run": {"Id": "ABCD"}})], "no project or run exactly matches"),
            # an UnknownItem (no id/name) is skipped
            ("unknown", [UnknownItem.model_validate({"Type": "sample", "Foo": "bar"})], "no project or run exactly matches"),
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
        assert result == [
            ("Sample_L001_R1_001.fastq.gz", tmp_path / "Sample_L001_R1_001.fastq.gz"),
            ("Sample_L001_R2_001.fastq.gz", tmp_path / "Sample_L001_R2_001.fastq.gz"),
        ]
        assert not (tmp_path / "Sample_L001_R1_001.fastq.gz").exists()


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

    def test_single_end_skips_pair_validation(self, mock_methods, tmp_path):
        files = [DatasetFileItem.model_validate({"Id": "1", "Name": "Sample_L001_R1_001.fastq.gz", "HrefContent": "https://x/1"})]
        item = DatasetItem.model_validate(
            {"Id": "ds.2", "Name": "Sample2", "Attributes": {"common_fastq": {"IsPairedEnd": False}}}
        )
        mock_methods.endpoints.datasets_files = MagicMock(return_value=make_response(files, total_count=len(files)))
        mock_fc = mock_methods.endpoints.files_content = MagicMock()
        mock_fc.return_value.__enter__.return_value.iter_content.return_value = [b"X"]

        result = mock_methods.download_dataset_files([item], dest_dir=tmp_path)

        assert len(result) == 1
        assert (tmp_path / "Sample_L001_R1_001.fastq.gz").read_bytes() == b"X"
