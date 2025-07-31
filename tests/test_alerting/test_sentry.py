import pytest
import os
import time
from unittest.mock import patch, MagicMock, call
from bioforklift.alerting.sentry import SentryMonitor, init_sentry


@pytest.fixture
def mock_sentry_sdk():
    """Mock sentry_sdk module to avoid actual Sentry calls"""
    with patch('bioforklift.alerting.sentry.sentry_sdk') as mock_sdk:
        mock_transaction = MagicMock()
        mock_span = MagicMock()
        mock_sdk.start_transaction.return_value.__enter__.return_value = mock_transaction
        mock_sdk.start_span.return_value.__enter__.return_value = mock_span
        yield mock_sdk


@pytest.fixture
def mock_env():
    """Mock environment variables"""
    env_vars = {
        'SENTRY_DSN': 'https://test@sentry.io/123',
        'GOOGLE_CLOUD_PROJECT': 'test-project',
        'ENVIRONMENT': 'test'
    }
    
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


class TestSentryMonitor:
    
    def test_init_with_dsn_parameter(self, mock_sentry_sdk):
        """Test initialization with DSN provided as parameter"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/456", service_name="test-service", project_name="test-project")
        
        assert monitor.service_name == "test-service"
        assert monitor.custom_tags == {}
        
        # Verify sentry_sdk.init was called with correct parameters
        mock_sentry_sdk.init.assert_called_once()
        call_args = mock_sentry_sdk.init.call_args[1]
        assert call_args['dsn'] == "https://test@sentry.io/456"
        assert call_args['traces_sample_rate'] == 1.0
        assert call_args['environment'] == 'production'  # default value
        assert call_args['release'] == 'development'  # default value

    def test_init_with_env_dsn(self, mock_sentry_sdk, mock_env):
        """Test initialization with DSN from environment variable"""
        monitor = SentryMonitor(service_name="test-service")
        
        assert monitor.service_name == "test-service"
        
        # Verify sentry_sdk.init was called with DSN from environment
        mock_sentry_sdk.init.assert_called_once()
        call_args = mock_sentry_sdk.init.call_args[1]
        assert call_args['dsn'] == "https://test@sentry.io/123"
        assert call_args['environment'] == 'test'
        assert call_args['release'] == 'development'

    def test_init_no_dsn_raises_error(self, mock_sentry_sdk):
        """Test that initialization without DSN raises ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Sentry DSN must be provided"):
                SentryMonitor()

    def test_init_with_custom_parameters(self, mock_sentry_sdk):
        """Test initialization with custom parameters"""
        custom_tags = {"team": "data", "service": "pipeline"}
        
        monitor = SentryMonitor(
            dsn="https://test@sentry.io/789",
            service_name="custom-service",
            project_name="test-project",
            traces_sample_rate=0.5,
            profile_sample_rate=0.5,
            release="v1.0.0",
            environment="staging",
            custom_tags=custom_tags
        )
        
        assert monitor.service_name == "custom-service"
        assert monitor.custom_tags == custom_tags
        
        # Verify sentry_sdk.init was called with custom parameters
        call_args = mock_sentry_sdk.init.call_args[1]
        assert call_args['dsn'] == "https://test@sentry.io/789"
        assert call_args['traces_sample_rate'] == 0.5
        assert call_args['release'] == "v1.0.0"
        assert call_args['environment'] == "staging"

    def test_add_context_to_event(self, mock_sentry_sdk, mock_env):
        """Test _add_context_to_event method"""
        custom_tags = {"custom": "value"}
        monitor = SentryMonitor(
            dsn="https://test@sentry.io/123",
            service_name="test-service",
            project_name="test-project",
            custom_tags=custom_tags
        )
        
        event = {"tags": {"existing": "tag"}}
        hint = {}
        
        result = monitor._add_context_to_event(event, hint)
        
        expected_tags = {
            "existing": "tag",
            "service": "test-service",
            "project": "test-project",
            "custom": "value"
        }
        
        assert result["tags"] == expected_tags

    def test_add_context_to_event_no_existing_tags(self, mock_sentry_sdk, mock_env):
        """Test _add_context_to_event with no existing tags"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        event = {}
        hint = {}
        
        result = monitor._add_context_to_event(event, hint)
        
        assert "tags" in result
        assert result["tags"]["service"] == "bioforklift-service"  # default service name

    @patch('time.time')
    def test_monitor_decorator_success(self, mock_time, mock_sentry_sdk):
        """Test monitor decorator with successful function execution"""
        mock_time.side_effect = [1000.0, 1002.5]  # start_time, end_time
        
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        @monitor.monitor("test_operation")
        def test_function(arg1, arg2, kwarg1="default"):
            return "success"
        
        result = test_function("value1", "value2", kwarg1="custom")
        
        assert result == "success"
        
        # Verify transaction was started
        mock_sentry_sdk.start_transaction.assert_called_once_with(name="test_operation", op="task")
        
        # Verify tags were set
        expected_calls = [
            call("function", "test_function"),
            call("operation", "test_operation"),
            call("status", "success")
        ]
        mock_sentry_sdk.set_tag.assert_has_calls(expected_calls, any_order=True)
        
        # Verify measurement was recorded
        mock_sentry_sdk.set_measurement.assert_called_with("duration", 2.5, "second")

    @patch('time.time')
    def test_monitor_decorator_with_exception(self, mock_time, mock_sentry_sdk):
        """Test monitor decorator with function that raises exception"""
        mock_time.side_effect = [1000.0, 1001.5]  # start_time, end_time
        
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        @monitor.monitor("failing_operation")
        def failing_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        
        # Verify error tags and measurements were set
        expected_calls = [
            call("function", "failing_function"),
            call("operation", "failing_operation"),
            call("status", "error")
        ]
        mock_sentry_sdk.set_tag.assert_has_calls(expected_calls, any_order=True)
        
        # Verify duration was recorded
        mock_sentry_sdk.set_measurement.assert_called_with("duration", 1.5, "second")
        
        # Verify exception was captured
        mock_sentry_sdk.capture_exception.assert_called_once()
        
        # Verify extra context was set
        mock_sentry_sdk.set_extra.assert_called_once_with("error_type", "ValueError")

    def test_monitor_decorator_with_capture_args(self, mock_sentry_sdk):
        """Test monitor decorator with capture_args enabled"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        @monitor.monitor("test_operation", capture_args=True)
        def test_function(arg1, arg2, kwarg1="default"):
            return "success"
        
        test_function("value1", "value2", kwarg1="custom")
        
        # Verify function context was set
        mock_sentry_sdk.set_context.assert_called_once_with(
            "function_args",
            {"args_count": 2, "kwargs_keys": ["kwarg1"]}
        )

    def test_monitor_decorator_no_performance_tracking(self, mock_sentry_sdk):
        """Test monitor decorator with performance tracking disabled"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        @monitor.monitor("test_operation", track_performance=False)
        def test_function():
            return "success"
        
        test_function()
        
        # Verify no measurements were recorded
        mock_sentry_sdk.set_measurement.assert_not_called()

    def test_monitor_decorator_default_operation_name(self, mock_sentry_sdk):
        """Test monitor decorator with default operation name"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        @monitor.monitor()
        def my_test_function():
            return "success"
        
        my_test_function()
        
        # Verify transaction was started with function name
        mock_sentry_sdk.start_transaction.assert_called_once_with(name="my_test_function", op="task")

    def test_track_metric(self, mock_sentry_sdk):
        """Test track_metric method"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        tags = {"batch_id": "batch_001", "type": "processing"}
        monitor.track_metric("samples_processed", 150.5, tags)
        
        # Verify span was started
        mock_sentry_sdk.start_span.assert_called_once_with(op="metric", description="samples_processed")
        
        # Get the span mock from the context manager
        span_mock = mock_sentry_sdk.start_span.return_value.__enter__.return_value
        
        # Verify measurement was set
        span_mock.set_measurement.assert_called_once_with("samples_processed", 150.5)
        
        # Verify tags were set
        expected_tag_calls = [
            call("batch_id", "batch_001"),
            call("type", "processing")
        ]
        span_mock.set_tag.assert_has_calls(expected_tag_calls, any_order=True)

    def test_track_metric_no_tags(self, mock_sentry_sdk):
        """Test track_metric method without tags"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        monitor.track_metric("simple_metric", 42.0)
        
        # Verify span was started
        mock_sentry_sdk.start_span.assert_called_once_with(op="metric", description="simple_metric")
        
        # Get the span mock
        span_mock = mock_sentry_sdk.start_span.return_value.__enter__.return_value
        
        # Verify measurement was set
        span_mock.set_measurement.assert_called_once_with("simple_metric", 42.0)
        
        # Verify no tags were set
        span_mock.set_tag.assert_not_called()

    def test_add_breadcrumb(self, mock_sentry_sdk):
        """Test add_breadcrumb method"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        data = {"batch_size": 100, "worker_id": "worker-1"}
        monitor.add_breadcrumb("Starting data processing", "process", "info", data)
        
        mock_sentry_sdk.add_breadcrumb.assert_called_once_with(
            message="Starting data processing",
            category="process",
            level="info",
            data=data
        )

    def test_add_breadcrumb_defaults(self, mock_sentry_sdk):
        """Test add_breadcrumb method with default parameters"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        monitor.add_breadcrumb("Simple breadcrumb")
        
        mock_sentry_sdk.add_breadcrumb.assert_called_once_with(
            message="Simple breadcrumb",
            category="custom",
            level="info",
            data=None
        )

    def test_set_context(self, mock_sentry_sdk):
        """Test set_context method"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        context_data = {
            "total_configs": 10,
            "successful": 8,
            "failed": 2
        }
        monitor.set_context("processing_results", context_data)
        
        mock_sentry_sdk.set_context.assert_called_once_with("processing_results", context_data)

    def test_set_tag(self, mock_sentry_sdk):
        """Test set_tag method"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        monitor.set_tag("workspace", "my-terra-workspace")
        
        mock_sentry_sdk.set_tag.assert_called_once_with("workspace", "my-terra-workspace")

    def test_capture_message(self, mock_sentry_sdk):
        """Test capture_message method"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        monitor.capture_message("Processing completed successfully", "info")
        
        mock_sentry_sdk.capture_message.assert_called_once_with("Processing completed successfully", "info")

    def test_capture_message_default_level(self, mock_sentry_sdk):
        """Test capture_message method with default level"""
        monitor = SentryMonitor(dsn="https://test@sentry.io/123")
        
        monitor.capture_message("Default level message")
        
        mock_sentry_sdk.capture_message.assert_called_once_with("Default level message", "info")


class TestInitSentry:
    
    def test_init_sentry_basic(self, mock_sentry_sdk):
        """Test init_sentry function with basic parameters"""
        monitor = init_sentry(dsn="https://test@sentry.io/123")
        
        assert isinstance(monitor, SentryMonitor)
        assert monitor.service_name == "bioforklift-service"
        
        # Verify sentry_sdk.init was called
        mock_sentry_sdk.init.assert_called_once()
        call_args = mock_sentry_sdk.init.call_args[1]
        assert call_args['dsn'] == "https://test@sentry.io/123"

    def test_init_sentry_custom_service_name(self, mock_sentry_sdk):
        """Test init_sentry function with custom service name"""
        monitor = init_sentry(
            dsn="https://test@sentry.io/123",
            service_name="my-custom-service"
        )
        
        assert isinstance(monitor, SentryMonitor)
        assert monitor.service_name == "my-custom-service"

    def test_init_sentry_with_kwargs(self, mock_sentry_sdk):
        """Test init_sentry function with additional kwargs"""
        monitor = init_sentry(
            dsn="https://test@sentry.io/123",
            service_name="test-service",
            traces_sample_rate=0.3,
            environment="testing"
        )
        
        assert isinstance(monitor, SentryMonitor)
        
        # Verify kwargs were passed through
        call_args = mock_sentry_sdk.init.call_args[1]
        assert call_args['traces_sample_rate'] == 0.3
        assert call_args['environment'] == "testing"