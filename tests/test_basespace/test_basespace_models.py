import pytest

from bioforklift.basespace import (
    BaseSpaceResponse,
    CommonFastqAttributes,
    DatasetFileItem,
    DatasetItem,
    StagedDatasetFile,
    OtherItem,
    ProjectItem,
    RunItem,
    SearchItem,
)
from bioforklift.basespace.basespace_exceptions import BaseSpaceMissingReadError


class TestSearchItemParsing:
    def test_parse_run_items(self, get_run_items):
        item = get_run_items[0]
        assert isinstance(item, RunItem)
        # checking pascal-cased aliases are applied correctly.
        assert item.id == "9876543210"
        assert item.name == "My Run"
        assert item.experiment_name == "My Experiment"

    def test_parse_project_items(self, get_project_items):
        item = get_project_items[0]
        assert isinstance(item, ProjectItem)
        # checking pascal-cased aliases are applied correctly.
        assert item.id == "1234567890"
        assert item.name == "My Project"

    def test_unmodeled_type_falls_back_to_other_item(self):
        # A scope/Type we don't model must route to OtherItem, not raise.
        response = BaseSpaceResponse[SearchItem].model_validate(
            {
                "Items": [{"Type": "sample", "Foo": "bar"}],
                "Paging": {"DisplayedCount": 1, "TotalCount": 1},
            }
        )
        assert isinstance(response.items[0], OtherItem)


class TestDatasetParsing:
    def test_dataset_item_aliases_and_nested_attributes(self, get_dataset_items):
        item = get_dataset_items[0]
        assert isinstance(item, DatasetItem)
        # checking pascal-cased aliases are applied correctly.
        assert item.id == "ds.1232bjbfejfu23u43h24u324"
        assert item.name == "My_Dataset"
        assert item.dataset_type.id == "common.fastq"

        attrs = item.attributes
        assert isinstance(attrs, CommonFastqAttributes)
        # attributes is pulled from the nested Attributes.common_fastq path.
        assert attrs.is_paired_end is True
        assert attrs.max_length_read1 == 151
        # checking pascal-cased aliases are applied correctly.
        assert attrs.total_clusters_pf == 38503
        assert attrs.total_reads_pf == 77006


class TestMatchesAnyDatasetType:
    def _dataset(self, type_id="common.fastq", conforms=("common.files",)):
        return DatasetItem.model_validate(
            {"Id": "ds.a", "Name": "sampleA", "DatasetType": {"Id": type_id, "ConformsToIds": list(conforms)}}
        )

    def test_matches_by_id(self):
        assert self._dataset(type_id="common.fastq").matches_any_dataset_type(["common.fastq"]) is True

    def test_matches_by_conforms_to(self):
        # Id is a typed variant, but it conforms to the requested common.fastq.
        ds = self._dataset(type_id="illumina.fastq.v1.8", conforms=("common.files", "common.fastq"))
        assert ds.matches_any_dataset_type(["common.fastq"]) is True

    def test_no_match(self):
        assert self._dataset(type_id="common.bam").matches_any_dataset_type(["common.fastq"]) is False

    def test_no_dataset_type_is_not_a_match(self):
        ds = DatasetItem.model_validate({"Id": "ds.a", "Name": "sampleA"})
        assert ds.matches_any_dataset_type(["common.fastq"]) is False

    def test_none_matches_all_types(self):
        assert self._dataset(type_id="common.bam").matches_any_dataset_type(None) is True

    def test_empty_list_matches_nothing(self):
        assert self._dataset(type_id="common.fastq").matches_any_dataset_type([]) is False


class TestDatasetFileItem:
    @pytest.mark.parametrize(
        "name, is_r1, is_r2, lane",
        [
            ("Sample_S1_L001_R1_001.fastq.gz", True, False, 1),
            ("Sample_S1_L002_R2_001.fastq.gz", False, True, 2),
            # No lane token -> lane is None but still a valid read.
            ("Sample_R1_001.fastq.gz", True, False, None),
            # Not an R1/R2 read file.
            ("Sample_S1_L001_I1_001.fastq.gz", False, False, 1),
            ("random_file.txt", False, False, None),
        ],
    )
    def test_read_and_lane_parsing(self, name, is_r1, is_r2, lane):
        file_item = DatasetFileItem.model_validate({"Id": "1", "Name": name})
        assert file_item.is_valid_read1 is is_r1
        assert file_item.is_valid_read2 is is_r2
        assert file_item.lane == lane


class TestStagedDatasetFile:
    def _item(self, name="Sample", paired=True):
        return DatasetItem.model_validate(
            {"Id": "ds.1", "Name": name, "Attributes": {"common_fastq": {"IsPairedEnd": paired}}}
        )

    def _files(self, *names):
        return [DatasetFileItem.model_validate({"Id": n, "Name": n}) for n in names]

    def test_valid_paired_end_builds(self):
        staged = StagedDatasetFile(
            dataset_item=self._item(),
            dataset_file_items=self._files("Sample_L001_R1_001.fastq.gz", "Sample_L001_R2_001.fastq.gz"),
        )
        assert [file.name for file in staged.read1_files] == ["Sample_L001_R1_001.fastq.gz"]
        assert [file.name for file in staged.read2_files] == ["Sample_L001_R2_001.fastq.gz"]
        assert staged.read1_output_filename == "Sample_R1.fastq.gz"
        assert staged.read2_output_filename == "Sample_R2.fastq.gz"

    def test_basename_strips_lane_split_dataset_name(self):
        # Lane-split dataset names collapse so their files merge into one output.
        staged = StagedDatasetFile.model_construct(
            dataset_item=self._item(name="rep02_L001"), dataset_file_items=[]
        )
        assert staged.basename == "rep02"
        assert staged.read1_output_filename == "rep02_R1.fastq.gz"

    def test_not_paired_end_raises_and_names_dataset(self):
        with pytest.raises(BaseSpaceMissingReadError, match="only paired-end") as exc:
            StagedDatasetFile(
                dataset_item=self._item(name="MySample", paired=False),
                dataset_file_items=self._files("MySample_L001_R1_001.fastq.gz", "MySample_L001_R2_001.fastq.gz"),
            )
        # Message names the dataset, not the whole model repr.
        assert "`MySample`" in str(exc.value)
        assert "dataset_type=" not in str(exc.value)

    @pytest.mark.parametrize(
        "names",
        [
            ("Sample_L001_R1_001.fastq.gz",),  # R1 only
            ("Sample_L001_R1_001.fastq.gz", "Sample_L002_R1_001.fastq.gz"),  # two R1s, no R2
            ("Sample_L001_R1_001.fastq.gz", "Sample_L001_R2_001.fastq.gz", "Sample_L001_I1_001.fastq.gz"),  # extra non-read
        ],
    )
    def test_unbalanced_reads_raise(self, names):
        with pytest.raises(BaseSpaceMissingReadError, match="Unbalanced R1/R2"):
            StagedDatasetFile(dataset_item=self._item(), dataset_file_items=self._files(*names))

    def test_model_construct_skips_validation(self):
        # An invalid (single-end, unbalanced) set builds without raising via model_construct.
        staged = StagedDatasetFile.model_construct(
            dataset_item=self._item(paired=False),
            dataset_file_items=self._files("Sample_L001_R1_001.fastq.gz"),
        )
        assert len(staged.dataset_file_items) == 1
