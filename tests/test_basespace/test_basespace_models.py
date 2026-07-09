from bioforklift.basespace import (
    BaseSpaceResponse,
    CommonFastqAttributes,
    DatasetItem,
    OtherItem,
    ProjectItem,
    RunItem,
    SearchItem,
)


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
