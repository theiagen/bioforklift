from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from bioforklift.basespace import (
    BaseSpaceResponse,
    DatasetFileItem,
    DatasetItem,
    Paging,
    ProjectItem,
    RunItem,
)
from bioforklift.basespace.basespace_exceptions import BaseSpaceServerError


class TestSearchEndpoint:
    @pytest.mark.parametrize(
        "scope, search_item_type",
        [
            ("projects", ProjectItem),
            ("runs", RunItem),
        ],
    )
    def test_search_valid_response(
        self,
        mock_client,
        mock_endpoints,
        bs_project_response,
        bs_run_response,
        scope,
        search_item_type
    ):
        # Determine which mock response to use based on the scope parameter
        bs_response = (
          bs_project_response if scope == "projects" else bs_run_response
        )

        # Create a Mock `mock_client.get` to control the response and assert how the endpoint called it.
        mock_client.get = Mock()
        mock_client.get.return_value.json.return_value = bs_response

        result = mock_endpoints.search(
            scope=scope,
            query='Name:"x"',
            paging=Paging(
                offset=1,
                limit=67,
                sort_by="Name",
                sort_dir="Desc"
            ),
        )

        assert isinstance(result, BaseSpaceResponse)
        assert isinstance(result.items[0], search_item_type)

        mock_client.get.assert_called_once_with(
            endpoint="search",
            params={
                "scope": scope,
                "query": 'Name:"x"',
                "Offset": 1,
                "Limit": 67,
                "SortBy": "Name",
                "SortDir": "Desc",
            },
        )

    def test_search_invalid_scope_raises(self, mock_endpoints):
        # `@validate_call` rejects the scope before `get` is ever reached.
        with pytest.raises(ValidationError):
            mock_endpoints.search(scope="fake_scope", query='Name:"x"')

    def test_search_bad_query_raises(self, mock_endpoints, mock_client):
        # The BaseSpace API returns a 500 error for an invalid query, which is mapped to a BaseSpaceServerError.
        # Not sure if there's a way to simulate an invalid query without hitting the actual API or creating a data model
        # that validates the query string. For now, we can just mock the client to raise the error.
        mock_client.get = Mock(
            side_effect=BaseSpaceServerError("server error", status_code=500, response=None)
        )
        with pytest.raises(BaseSpaceServerError):
            mock_endpoints.search(scope="projects", query='Name:!@#$%^&*()')


class TestDatasets:
    def test_datasets_valid_response(self, mock_endpoints, mock_client, bs_dataset_response):
        mock_client.get = Mock()
        mock_client.get.return_value.json.return_value = bs_dataset_response

        result = mock_endpoints.datasets(
            project_id="123",
            input_runs="456",
            dataset_types="common.fastq",
            paging=Paging(
                offset=1,
                limit=67,
                sort_by="Name",
                sort_dir="Desc"
            ),
        )

        assert isinstance(result, BaseSpaceResponse)
        assert isinstance(result.items[0], DatasetItem)

        mock_client.get.assert_called_once_with(
            endpoint="datasets",
            params={
                "projectid": "123",
                "inputruns": "456",
                "datasettypes": "common.fastq",
                "Offset": 1,
                "Limit": 67,
                "SortBy": "Name",
                "SortDir": "Desc",
            },
        )


class TestDatasetsFiles:
    def test_datasets_files_valid_response(self, mock_endpoints, mock_client, bs_dataset_files_response):
        mock_client.get = Mock()
        mock_client.get.return_value.json.return_value = bs_dataset_files_response

        result = mock_endpoints.datasets_files(
            dataset_id="ds.12345",
            paging=Paging(
                offset=1,
                limit=67,
                sort_by="Name",
                sort_dir="Desc"
            ),
        )

        assert isinstance(result, BaseSpaceResponse)
        assert isinstance(result.items[0], DatasetFileItem)

        # `dataset_id` is interpolated into the endpoint path, not the params.
        mock_client.get.assert_called_once_with(
            endpoint="datasets/ds.12345/files",
            params={
                "Offset": 1,
                "Limit": 67,
                "SortBy": "Name",
                "SortDir": "Desc",
            },
        )


class TestFilesContent:
    def test_files_content_valid_response(self, mock_endpoints, mock_client):
        mock_client.get = Mock()

        result = mock_endpoints.files_content(
            file_id="42",
            redirect="true",
            stream=True,
        )

        # Unlike the other endpoints, this returns the raw response object (for streaming).
        assert result is mock_client.get.return_value

        mock_client.get.assert_called_once_with(
            endpoint="files/42/content",
            params={
                "redirect": "true"
            },
            stream=True,
        )