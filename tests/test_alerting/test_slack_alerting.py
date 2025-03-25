import pytest
from unittest.mock import patch, MagicMock
import json
import requests
from forklift.alerting import SlackNotifier, SlackAlert, TerraSummary

@pytest.fixture(autouse=True)
def mock_google_auth():
    """Mock Google Cloud authentication to avoid credential errors"""
    with patch('google.auth.default') as mock_auth:
        # Return a mock credentials object and project ID
        mock_credentials = MagicMock()
        mock_auth.return_value = (mock_credentials, "test-project")
        yield mock_auth

class TestSlackNotifier:
    def test_init(self):
        """Test initialization with valid parameters"""
        notifier = SlackNotifier(token="xoxb-test-token", channel_id="C12345")
        assert notifier.token == "xoxb-test-token"
        assert notifier.channel == "C12345"

    def test_init_error(self):
        """Test initialization with invalid parameters"""
        with pytest.raises(ValueError):
            SlackNotifier(token="", channel_id="C12345")
        
        with pytest.raises(ValueError):
            SlackNotifier(token="xoxb-test-token", channel_id="")

    @patch('requests.post')
    def test_send_message(self, mock_post):
        """Test sending a simple message"""
        # Mock the response
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_post.return_value = mock_response
        
        notifier = SlackNotifier(token="xoxb-test-token", channel_id="C12345")
        result = notifier.send_message("Test message")
        
        # Verify requests.post was called with correct arguments
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        assert args[0] == 'https://slack.com/api/chat.postMessage'
        assert kwargs['headers']['Authorization'] == 'Bearer xoxb-test-token'
        assert kwargs['json']['channel'] == 'C12345'
        assert kwargs['json']['text'] == 'Test message'
        
        # Verify result
        assert result["ok"] is True
        assert result["ts"] == "1234567890.123456"

    @patch('requests.post')
    def test_send_message_error(self, mock_post):
        """Test error handling when sending a message"""
        # Mock an error response
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "invalid_auth"}
        mock_post.return_value = mock_response
        
        notifier = SlackNotifier(token="xoxb-test-token", channel_id="C12345")
        
        with pytest.raises(Exception) as exc_info:
            notifier.send_message("Test message")
        
        assert "Slack API error: invalid_auth" in str(exc_info.value)

    @patch('requests.post')
    def test_send_formatted_message(self, mock_post):
        """Test sending a formatted message with attachments"""
        # Mock the response
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_post.return_value = mock_response
        
        notifier = SlackNotifier(token="xoxb-test-token", channel_id="C12345")
        result = notifier.send_formatted_message(
            title="Test Title", 
            message="Test message content",
            attachments=[{"title": "Attachment", "text": "Attachment content", "color": "#36C5F0"}]
        )
        
        # Verify requests.post was called with correct arguments
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        assert args[0] == 'https://slack.com/api/chat.postMessage'
        assert kwargs['headers']['Authorization'] == 'Bearer xoxb-test-token'
        assert kwargs['json']['channel'] == 'C12345'
        assert kwargs['json']['text'] == 'Test Title'
        
        # Verify blocks were created correctly
        blocks = kwargs['json']['blocks']
        assert len(blocks) == 4  # Header, section, divider, attachment section
        assert blocks[0]['type'] == 'header'
        assert blocks[0]['text']['text'] == 'Test Title'
        assert blocks[1]['type'] == 'section'
        assert blocks[1]['text']['text'] == 'Test message content'
        assert blocks[2]['type'] == 'divider'
        assert blocks[3]['type'] == 'section'
        assert '*Attachment*' in blocks[3]['text']['text']
        assert 'Attachment content' in blocks[3]['text']['text']


class TestSlackAlert:
    @pytest.fixture
    def mock_notifier(self):
        """Create a mock notifier"""
        mock = MagicMock(spec=SlackNotifier)
        mock.send_message.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock.send_formatted_message.return_value = {"ok": True, "ts": "1234567890.123456"}
        return mock
    
    @pytest.fixture
    def mock_terra2bq(self):
        """Create a mock Terra2BQ instance"""
        mock = MagicMock()
        # Mock samples_ops and config_ops
        mock.samples_ops = MagicMock()
        mock.config_ops = MagicMock()
        return mock
    
    def test_send_message(self, mock_notifier):
        """Test sending a simple message via SlackAlert"""
        alert = SlackAlert(notifier=mock_notifier)
        result = alert.send_message("Test alert message")
        
        mock_notifier.send_message.assert_called_once_with("Test alert message")
        assert result["ok"] is True
        
    def test_send_formatted_message(self, mock_notifier):
        """Test sending a formatted message via SlackAlert"""
        alert = SlackAlert(notifier=mock_notifier)
        result = alert.send_formatted_message(
            title="Alert Title",
            message="Alert message",
            attachments=[{"title": "Details", "text": "Alert details"}]
        )
        
        mock_notifier.send_formatted_message.assert_called_once_with(
            "Alert Title", "Alert message", [{"title": "Details", "text": "Alert details"}]
        )
        assert result["ok"] is True
    
    @patch.object(TerraSummary, 'generate_hourly_summary')
    @patch.object(TerraSummary, 'format_hourly_summary_for_slack')
    def test_send_hourly_summary(self, mock_format, mock_generate, mock_notifier, mock_terra2bq):
        """Test sending an hourly summary"""
        # Mock the summary generation
        mock_generate.return_value = {
            "total_samples": 5,
            "uploaded_samples": 3,
            "submitted_samples": 2,
            "by_entity_type": [],
            "by_config": [],
            "start_time": "2023-01-01T12:00:00Z",
            "end_time": "2023-01-01T13:00:00Z"
        }
        
        # Mock the formatting
        mock_format.return_value = {
            "title": "Test Project Hourly Summary",
            "message": "Test summary message",
            "attachments": []
        }
        
        alert = SlackAlert(notifier=mock_notifier)
        result = alert.send_hourly_summary(mock_terra2bq, project_title="Test Project")
        
        # Verify the summary was generated and formatted
        mock_generate.assert_called_once()
        mock_format.assert_called_once()
        
        # Verify the formatted message was sent
        mock_notifier.send_formatted_message.assert_called_once_with(
            "Test Project Hourly Summary", "Test summary message", []
        )
        assert result["ok"] is True