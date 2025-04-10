from unittest.mock import MagicMock, Mock, patch
import pytest
from datetime import datetime, timedelta, timezone
import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField, LoadJobConfig
from bioforklift.bigquery import BigQuerySampleOperations

@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication to avoid credential errors"""
    with patch('google.auth.default') as mock_auth:
        # Return a mock credentials object and project ID
        mock_credentials = MagicMock()
        mock_auth.return_value = (mock_credentials, "test-project")
        yield mock_auth

@pytest.fixture
def mock_bq_client(mocker):
    """Create a mock BigQuery client."""
    client = mocker.Mock()
    client.project = "test-project"
    client.dataset = "test_dataset"
    return client


@pytest.fixture
def test_schema():
    """Create a schema for the test table."""
    return [
        bigquery.SchemaField("id", "STRING"),
        bigquery.SchemaField("sample_id", "STRING"),
        bigquery.SchemaField("config_id", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("uploaded_at", "TIMESTAMP"),
    ]


@pytest.fixture
def test_field_attributes():
    """Create field attributes for the test table."""
    return {
        "sample_id": {"sample_identifier": True},
        "config_id": {"config_identifier": True, "value": "test-config"},
    }


@pytest.fixture
def sample_rows():
    """Create sample rows that will be returned by queries."""
    now = datetime.now(timezone.utc)

    return [
        # Today - not uploaded
        {
            "id": "id1",
            "sample_id": "sample1",
            "config_id": "test-config",
            "created_at": now,
            "updated_at": now,
            "uploaded_at": None,
            "status": "pending",
        },
        # Today - uploaded
        {
            "id": "id2",
            "sample_id": "sample2",
            "config_id": "test-config",
            "created_at": now,
            "updated_at": now,
            "uploaded_at": now,
            "status": "completed",
        },
        # Yesterday
        {
            "id": "id3",
            "sample_id": "sample3",
            "config_id": "test-config",
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(days=1),
            "uploaded_at": None,
            "status": "pending",
        },
        # Last week
        {
            "id": "id4",
            "sample_id": "sample4",
            "config_id": "test-config",
            "created_at": now - timedelta(days=5),
            "updated_at": now - timedelta(days=5),
            "uploaded_at": now - timedelta(days=5),
            "status": "completed",
        },
        # Last month
        {
            "id": "id5",
            "sample_id": "sample5",
            "config_id": "test-config",
            "created_at": now - timedelta(days=30),
            "updated_at": now - timedelta(days=30),
            "uploaded_at": now - timedelta(days=30),
            "status": "completed",
        },
        # Hours ago
        {
            "id": "id6",
            "sample_id": "sample6",
            "config_id": "test-config",
            "created_at": now - timedelta(hours=3),
            "updated_at": now - timedelta(hours=3),
            "uploaded_at": None,
            "status": "pending",
        },
        # Different config
        {
            "id": "id7",
            "sample_id": "sample7",
            "config_id": "other-config",
            "created_at": now,
            "updated_at": now,
            "uploaded_at": None,
            "status": "pending",
        },
    ]


@pytest.fixture
def bq_operations(mock_bq_client, test_schema, test_field_attributes):
    """Create a BigQuerySampleOperations instance with mock client."""
    with patch("bioforklift.bigquery.utils.load_schema_from_yaml") as mock_load_schema:
        mock_load_schema.return_value = {
            "schema": test_schema,
            "field_attributes": test_field_attributes,
        }

        operations = BigQuerySampleOperations(
            client=mock_bq_client, table_name="test_samples_timeframe"
        )

        # Override attributes directly
        operations.field_attributes = test_field_attributes
        operations.schema = test_schema
        return operations


def setup_query_mock(mock_bq_client, sample_rows, query_matcher=None):
    """
    Configure the mock client's query method to return specified rows.

    Args:
        mock_bq_client: The mock BigQuery client
        sample_rows: List of row dictionaries to return
        query_matcher: Optional function that takes the query string and returns
                      True if this query should return the provided rows
    """

    def side_effect(query, job_config=None, location=None):
        # If a matcher is provided, use it, otherwise return rows for any query
        should_return_rows = True
        if query_matcher:
            should_return_rows = query_matcher(query)

        result = Mock()
        if should_return_rows:
            result.result.return_value = sample_rows
        else:
            result.result.return_value = []

        return result

    mock_bq_client.query.side_effect = side_effect


def test_today_not_uploaded(bq_operations, mock_bq_client, sample_rows):
    """Test querying for today's samples that haven't been uploaded."""

    # Setup query to return only today's not uploaded sample
    def query_matcher(query):
        return (
            "DATE(created_at) = CURRENT_DATE()" in query
            and "uploaded_at IS NULL" in query
        )

    setup_query_mock(
        mock_bq_client,
        [sample_rows[0]],  # Only the first row (today, not uploaded)
        query_matcher,
    )

    # Call the method
    result = bq_operations.get_samples_by_timeframe(
        timeframe="today", uploaded_filter="not_uploaded"
    )

    # Should return 1 row (id1)
    assert len(result) == 1
    assert result.iloc[0]["id"] == "id1"
    assert result.iloc[0]["uploaded_at"] is None


def test_today_all(bq_operations, mock_bq_client, sample_rows):
    """Test querying for all of today's samples."""

    # Setup query to return today's samples
    def query_matcher(query):
        return (
            "DATE(created_at) = CURRENT_DATE()" in query
            and "uploaded_at IS NULL" not in query
        )

    setup_query_mock(mock_bq_client, [sample_rows[0], sample_rows[1]], query_matcher)

    # Call the method
    result = bq_operations.get_samples_by_timeframe(
        timeframe="today", uploaded_filter="all"
    )

    # Should return 2 rows (id1, id2)
    assert len(result) == 2
    ids = set(result["id"].values)
    assert "id1" in ids
    assert "id2" in ids


def test_yesterday_samples(bq_operations, mock_bq_client, sample_rows):
    """Test querying for yesterday's samples."""

    # Setup query to return yesterday's sample
    def query_matcher(query):
        return "DATE(created_at) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)" in query

    setup_query_mock(mock_bq_client, [sample_rows[2]], query_matcher)

    # Call the method
    result = bq_operations.get_samples_by_timeframe(
        timeframe="yesterday", uploaded_filter="all"
    )

    # Should return 1 row (id3)
    assert len(result) == 1
    assert result.iloc[0]["id"] == "id3"


def test_weekly_samples(bq_operations, mock_bq_client, sample_rows):
    """Test querying for samples from the last week."""

    # Setup query to return samples from the last week
    def query_matcher(query):
        return "DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)" in query

    setup_query_mock(mock_bq_client, sample_rows[0:4] + [sample_rows[5]], query_matcher)

    result = bq_operations.get_samples_by_timeframe(
        timeframe="week", uploaded_filter="all"
    )

    assert len(result) == 5

    # Check specific IDs
    ids = set(result["id"].values)
    assert "id1" in ids
    assert "id2" in ids
    assert "id3" in ids
    assert "id4" in ids
    assert "id6" in ids


def test_hourly_samples(bq_operations, mock_bq_client, sample_rows):
    """Test querying for samples from the last few hours."""

    # Setup query to return samples from the last few hours
    def query_matcher(query):
        return "INTERVAL" in query and "HOUR" in query

    setup_query_mock(
        mock_bq_client,
        sample_rows[0:2] + [sample_rows[5]],  # Today + hours row
        query_matcher,
    )

    # Call the method
    result = bq_operations.get_samples_by_timeframe(
        timeframe="hourly", hours_back=4, uploaded_filter="all"
    )

    # Should return 3 rows (id1, id2, id6)
    assert len(result) == 3

    ids = set(result["id"].values)
    assert "id1" in ids
    assert "id2" in ids
    assert "id6" in ids


def test_custom_range(bq_operations, mock_bq_client, sample_rows):
    """Test querying with a custom date range."""

    # Setup query to return samples within a date range
    def query_matcher(query):
        return "BETWEEN" in query or "start_datetime" in query

    setup_query_mock(
        mock_bq_client,
        sample_rows[0:3] + [sample_rows[5]],  # Today + yesterday + hours row
        query_matcher,
    )

    # Get current date for range calculation
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    end_date = now.strftime("%Y-%m-%d %H:%M:%S")

    # Call the method
    result = bq_operations.get_samples_by_timeframe(
        timeframe="custom",
        start_datetime=start_date,
        end_datetime=end_date,
        uploaded_filter="all",
    )

    # Should return 4 rows (id1, id2, id3, id6)
    assert len(result) == 4

    ids = set(result["id"].values)
    assert "id1" in ids
    assert "id2" in ids
    assert "id3" in ids
    assert "id6" in ids


def test_convenience_methods(bq_operations, mocker):
    """Test that convenience methods call get_samples_by_timeframe correctly."""
    # Create a spy on get_samples_by_timeframe
    with patch.object(bq_operations, "get_samples_by_timeframe") as spy:
        # Mock it to return a simple DataFrame
        spy.return_value = pd.DataFrame([{"id": "test_id"}])

        # Test get_samples_created_today
        result = bq_operations.get_samples_created_today()
        spy.assert_called_with(timeframe="today", uploaded_filter="not_uploaded")
        assert len(result) == 1

        # Test get_recent_samples_by_hour
        result = bq_operations.get_recent_samples_by_hour(
            hours=3, uploaded_filter="all"
        )
        spy.assert_called_with(timeframe="hourly", hours_back=3, uploaded_filter="all")
        assert len(result) == 1
