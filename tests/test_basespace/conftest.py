from unittest.mock import MagicMock

import pytest
import requests

from bioforklift.basespace import (
    BaseSpace,
    BaseSpaceClient,
    BaseSpaceEndpoints,
    BaseSpaceResponse,
    BaseSpaceMethods,
    DatasetItem,
    SearchItem,
)


@pytest.fixture
def mock_client():
    """A BaseSpaceClient with default URL/version and a test token."""
    return BaseSpaceClient(access_token="67")


@pytest.fixture
def mock_methods(mock_client):
    """A BaseSpaceMethods instance with a mock client."""
    return BaseSpaceMethods(mock_client)


@pytest.fixture
def mock_endpoints(mock_client):
    """A BaseSpaceEndpoints instance with a mock client."""
    return BaseSpaceEndpoints(mock_client)


@pytest.fixture
def mock_basespace(mock_client):
    """A BaseSpace instance with a mock client, methods and endpoints."""
    return BaseSpace.from_client(mock_client)


@pytest.fixture
def mock_response():
    """A mock requests.Response that succeeds by default."""
    response = MagicMock(spec=requests.Response)
    response.status_code = 200
    response.url = "https://api.basespace.illumina.com/v2/search"
    return response


@pytest.fixture
def bs_project_response():
    """
    A `/search?scope=projects` response body with a single project item.
    """

    return {
        "Items": [
            {
                "Type": "project",
                "Project": {
                    "Id": "1234567890",
                    "Name": "My Project",
                },
            }
        ],
        "Paging": {
            "DisplayedCount": 1,
            "TotalCount": 1,
            "Offset": 0,
            "Limit": 10,
            "SortDir": "Asc",
            "SortBy": "Score",
        },
    }


@pytest.fixture
def bs_run_response():
    """
    A `/search?scope=runs` response body with a single run item.
    """

    return {
        "Items": [
            {
                "Type": "run",
                "Run": {
                    "Id": "9876543210",
                    "Name": "My Run",
                    "ExperimentName": "My Experiment",
                },
            }
        ],
        "Paging": {
            "DisplayedCount": 1,
            "TotalCount": 1,
            "Offset": 0,
            "Limit": 10,
            "SortDir": "Asc",
            "SortBy": "Score",
        },
    }


@pytest.fixture
def bs_dataset_response():
    """
    A `/datasets` response body with a single paired-end common.fastq dataset.
    """

    return {
        "Items": [
            {
                "Id": "ds.1232bjbfejfu23u43h24u324",
                "Name": "My_Dataset",
                "DatasetType": {
                    "Id": "common.fastq",
                    "Href": "https://api.basespace.illumina.com/v2/datasettypes/common.fastq",
                    "Name": "Common Fastq",
                    "ConformsToIds": ["common.files"],
                },
                "Attributes": {
                    "common_fastq": {
                        "IsPairedEnd": True,
                        "MaxLengthRead1": 151,
                        "MaxLengthRead2": 151,
                        "TotalClustersPF": 38503,
                        "TotalClustersRaw": 0,
                        "TotalReadsPF": 77006,
                        "TotalReadsRaw": 0,
                    }
                },
            }
        ],
        "Paging": {
            "DisplayedCount": 1,
            "TotalCount": 1,
            "Offset": 0,
            "Limit": 1000,
            "SortDir": "Asc",
            "SortBy": "Score",
        },
    }


@pytest.fixture
def bs_dataset_files_response():
    """
    A `/datasets/{id}/files` response body with an R1/R2 pair.
    """

    return {
        "Items": [
            {
                "Id": "1738",
                "HrefContent": "https://api.basespace.illumina.com/v2/files/1738/content",
                "Name": "My_Dataset_L001_R1_001.fastq.gz",
            },
            {
                "Id": "1739",
                "HrefContent": "https://api.basespace.illumina.com/v2/files/1739/content",
                "Name": "My_Dataset_L001_R2_001.fastq.gz",
            },
        ],
        "Paging": {
            "DisplayedCount": 2,
            "TotalCount": 2,
            "Offset": 0,
            "Limit": 1000,
            "SortDir": "Asc",
            "SortBy": "Score",
        },
    }


@pytest.fixture
def get_project_items(bs_project_response):
    """The parsed list of ProjectItems from `bs_project_response`."""
    return BaseSpaceResponse[SearchItem].model_validate(bs_project_response).items


@pytest.fixture
def get_run_items(bs_run_response):
    """The parsed list of RunItems from `bs_run_response`."""
    return BaseSpaceResponse[SearchItem].model_validate(bs_run_response).items


@pytest.fixture
def get_dataset_items(bs_dataset_response):
    """The parsed list of DatasetItems from `bs_dataset_response`."""
    return BaseSpaceResponse[DatasetItem].model_validate(bs_dataset_response).items
