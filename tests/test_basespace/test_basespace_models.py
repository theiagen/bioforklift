from bioforklift.basespace import (
    BaseSpaceResponse,
    CommonFastqAttributes,
    DatasetFileItem,
    DatasetItem,
    DatasetType,
    OtherItem,
    PagingResponse,
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

    def test_dataset_type_conforms_to_ids_defaults_empty(self):
        # ConformsToIds is optional: absent -> empty list; present -> parsed.
        without = DatasetItem.model_validate(
            {"Id": "ds.1", "Name": "S", "DatasetType": {"Id": "common.fastq"}}
        )
        assert isinstance(without.dataset_type, DatasetType)
        assert without.dataset_type.conforms_to_ids == []

        with_conformance = DatasetItem.model_validate(
            {
                "Id": "ds.2",
                "Name": "S",
                "DatasetType": {"Id": "illumina.fastq.v1.8", "ConformsToIds": ["common.fastq"]},
            }
        )
        assert with_conformance.dataset_type.conforms_to_ids == ["common.fastq"]

    def test_dataset_item_optional_fields_default_none(self):
        # A minimal dataset (no DatasetType/Attributes) parses with None defaults.
        item = DatasetItem.model_validate({"Id": "ds.1", "Name": "S"})
        assert item.dataset_type is None
        assert item.attributes is None


class TestDatasetFileItem:
    def test_size_is_optional(self):
        # Size is used to verify a complete download; it defaults to None when absent.
        without = DatasetFileItem.model_validate({"Id": "1", "Name": "S_R1.fastq.gz"})
        assert without.size is None

        with_size = DatasetFileItem.model_validate(
            {"Id": "1", "Name": "S_R1.fastq.gz", "Size": 4096}
        )
        assert with_size.size == 4096


class TestPagingParsing:
    def test_paging_block_parses(self, bs_dataset_response):
        # The Paging block of a list response parses into a PagingResponse (pascal aliases).
        response = BaseSpaceResponse[DatasetItem].model_validate(bs_dataset_response)
        assert isinstance(response.paging, PagingResponse)
        assert response.paging.displayed_count == 1
        assert response.paging.total_count == 1
        assert response.paging.offset == 0
        assert response.paging.limit == 1000
        assert response.paging.sort_dir == "Asc"
        assert response.paging.sort_by == "Score"
