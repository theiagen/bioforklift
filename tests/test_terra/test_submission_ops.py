import pytest
from datetime import datetime
from unittest.mock import Mock, create_autospec
import requests
from forklift.terra import TerraSubmissions
from forklift.terra import WorkflowConfig, WorkflowMetadata, SubmissionInfo


@pytest.fixture
def mock_response():
    """Create a mock response with json method"""
    response = Mock(spec=requests.Response)
    response.ok = True
    return response


@pytest.fixture
def mock_terra_client():
    client = Mock()
    return client


@pytest.fixture
def workflow_ops(mock_terra_client):
    return TerraSubmissions(mock_terra_client)


class TestWorkflowSubmission:
    def test_submit_workflow(self, workflow_ops, mock_terra_client, mock_response):
        """Test basic workflow submission"""
        config = WorkflowConfig(
            methodConfigurationNamespace="broad",
            methodConfigurationName="processing",
            entityType="sample",
            entityName="test_set",
            expression="this.samples",
        )

        # Mock successful submission
        expected_response = {"submissionId": "123"}
        mock_response.json.return_value = expected_response
        mock_terra_client.post.return_value = mock_response

        result = workflow_ops.submit_workflow(config)

        # Verify correct endpoint and data
        mock_terra_client.post.assert_called_once()
        args = mock_terra_client.post.call_args
        assert args[0][0] == "submissions"

        # Verify response
        assert result == expected_response


class TestSubmissionStatus:
    def test_get_submission_status(
        self, workflow_ops, mock_terra_client, mock_response
    ):
        """Test getting submission status"""
        response_data = {"submissionId": "123", "status": "Done", "workflows": []}
        mock_response.json.return_value = response_data
        mock_terra_client.get.return_value = mock_response

        result = workflow_ops.get_submission_status("123")

        mock_terra_client.get.assert_called_once_with("submissions/123")
        assert result["status"] == "Done"


class TestGetAllSubmissions:
    def test_get_all_submissions(self, workflow_ops, mock_terra_client, mock_response):
        """Test getting all submissions"""
        response_data = [
            {
                "submissionId": "123",
                "status": "Done",
                "submissionDate": "2024-02-18T10:00:00Z",
                "submissionEntity": {"entityName": "test_set"},
            },
            {
                "submissionId": "124",
                "status": "Running",
                "submissionDate": "2024-02-18T11:00:00Z",
                "submissionEntity": {"entityName": "test_set_2"},
            },
        ]
        mock_response.json.return_value = response_data
        mock_terra_client.get.return_value = mock_response

        submissions = workflow_ops.get_all_submissions()

        mock_terra_client.get.assert_called_once_with("submissions")
        assert len(submissions) == 2
        assert all(isinstance(sub, SubmissionInfo) for sub in submissions)
        assert submissions[0].submission_id == "123"
        assert submissions[1].status == "Running"

    def test_get_all_submissions_skip_aborted(
        self, workflow_ops, mock_terra_client, mock_response
    ):
        """Test skipping aborted submissions"""
        response_data = [
            {
                "submissionId": "123",
                "status": "Done",
                "submissionDate": "2024-02-18T10:00:00Z",
                "submissionEntity": {"entityName": "test_set"},
            },
            {
                "submissionId": "124",
                "status": "Aborted",
                "submissionDate": "2024-02-18T11:00:00Z",
                "submissionEntity": {"entityName": "test_set_2"},
            },
        ]
        mock_response.json.return_value = response_data
        mock_terra_client.get.return_value = mock_response

        submissions = workflow_ops.get_all_submissions(skip_aborted=True)

        assert len(submissions) == 1
        assert submissions[0].submission_id == "123"