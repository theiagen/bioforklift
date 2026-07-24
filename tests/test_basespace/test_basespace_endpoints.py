from unittest.mock import MagicMock

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
from bioforklift.basespace.basespace_endpoints import fetch_all_items
from bioforklift.basespace.basespace_exceptions import BaseSpaceServerError


class TestFetchAllItems:
    """`fetch_all_items` — the module-level pagination helper used by every endpoint read."""

    def test_single_page(self, make_response):
        # The endpoint returns all items in a single page, so only one call is made.
        endpoint = MagicMock(side_effect=[make_response([0, 1], total_count=2)])

        result = fetch_all_items(endpoint)

        assert result == [0, 1]
        assert endpoint.call_count == 1
        paging_1 = endpoint.call_args_list[0].kwargs["paging"]
        assert paging_1.offset == 0
        assert paging_1.limit == 1000

    def test_multiple_pages(self, make_response):
        pages = [
            make_response(list(range(0, 1000)), total_count=2500),
            make_response(list(range(1000, 2000)), total_count=2500),
            make_response(list(range(2000, 2500)), total_count=2500),
        ]
        endpoint = MagicMock(side_effect=pages)

        result = fetch_all_items(endpoint)

        assert len(result) == 2500
        assert endpoint.call_count == 3
        offsets = [call.kwargs["paging"].offset for call in endpoint.call_args_list]
        assert offsets == [0, 1000, 2000]
        assert all(call.kwargs["paging"].limit == 1000 for call in endpoint.call_args_list)

    def test_empty_first_page(self, make_response):
        endpoint = MagicMock(side_effect=[make_response([], total_count=0)])

        result = fetch_all_items(endpoint)

        assert result == []
        assert endpoint.call_count == 1


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
        mock_client.get = MagicMock()
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
        mock_client.get = MagicMock(
            side_effect=BaseSpaceServerError("server error", status_code=500, response=None)
        )
        with pytest.raises(BaseSpaceServerError):
            mock_endpoints.search(scope="projects", query='Name:!@#$%^&*()')


class TestDatasets:
    def test_datasets_valid_response(self, mock_endpoints, mock_client, bs_dataset_response):
        mock_client.get = MagicMock()
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


class TestDatasetFiles:
    def test_dataset_files_valid_response(self, mock_endpoints, mock_client, bs_dataset_files_response):
        mock_client.get = MagicMock()
        mock_client.get.return_value.json.return_value = bs_dataset_files_response

        result = mock_endpoints.dataset_files(
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


class TestFileContent:
    def test_file_content_valid_response(self, mock_endpoints, mock_client):
        mock_client.get = MagicMock()

        result = mock_endpoints.file_content(
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