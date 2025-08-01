import os
import time
import functools
from typing import Optional, Dict, Any, Callable
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration


class SentryMonitor:
    """
    A reusable Sentry monitoring class for Terra2BQ operations.
    
    This class provides initialization, decorator functionality, and utility methods
    for comprehensive error tracking and performance monitoring given a DSN.
    """
    
    def __init__(
        self,
        dsn: Optional[str] = None,
        service_name: str = "bioforklift-service",
        project_name: str = "bioforklift",
        traces_sample_rate: float = 1.0,
        release: Optional[str] = None,
        environment: Optional[str] = None,
        custom_tags: Optional[Dict[str, str]] = None
    ):
        """
        Initialize Sentry monitoring.
        
        Args:
            dsn: Sentry DSN. If None, will try to get from SENTRY_DSN env var
            service_name: Name of the service for tagging
            project_name: Name of the project for tagging
            traces_sample_rate: Sampling rate for performance monitoring
            release: Release version. Defaults to 'development'
            environment: Environment name. Defaults to ENVIRONMENT env var or 'production'
            custom_tags: Additional tags to add to all events
        """
        self.service_name = service_name
        self.project_name = project_name
        self.custom_tags = custom_tags or {}
        
        dsn = dsn or os.environ.get('SENTRY_DSN')
        if not dsn:
            raise ValueError("Sentry DSN must be provided either as parameter or SENTRY_DSN environment variable")
    
        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=traces_sample_rate,
            release=release or 'development',
            environment=environment or os.environ.get('ENVIRONMENT', 'production'),
            integrations=[
                LoggingIntegration(level="INFO", event_level="ERROR"),
                SqlalchemyIntegration()
            ],
            before_send=self._add_context_to_event,
        )
    
    def _add_context_to_event(self, event: Dict[str, Any], hint: Dict[str, Any]) -> Dict[str, Any]:
        """Add custom context to all Sentry events."""
        event.setdefault('tags', {}).update({
            'service': self.service_name,
            'project': self.project_name,
            **self.custom_tags
        })
        return event
    
    def monitor(
        self, 
        operation_name: Optional[str] = None, 
        track_performance: bool = True,
        capture_args: bool = False
    ) -> Callable:
        """
        Decorator that automatically monitors functions with Sentry.
        
        Args:
            operation_name: Name for the operation. Defaults to function name
            track_performance: Whether to track performance metrics
            capture_args: Whether to capture function arguments (be careful with sensitive data)
        
        Returns:
            Decorated function with Sentry monitoring
        
        Example:
            @sentry_monitor.monitor("terra_sync")
            def sync_data():
                # Your function code here
                pass
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                op_name = operation_name or f"{func.__name__}"
                
                with sentry_sdk.start_transaction(name=op_name, op="task") as transaction:
                    sentry_sdk.set_tag("function", func.__name__)
                    sentry_sdk.set_tag("operation", op_name)
                    
                    if capture_args:
                        sentry_sdk.set_context("function_args", {
                            "args_count": len(args),
                            "kwargs_keys": list(kwargs.keys())
                        })
                    
                    start_time = time.time()
                    
                    try:
                        result = func(*args, **kwargs)
                        
                        # Record success metrics
                        if track_performance:
                            duration = time.time() - start_time
                            sentry_sdk.set_measurement("duration", duration, "second")
                            sentry_sdk.set_tag("status", "success")
                        
                        return result
                        
                    except Exception as exc:
                        # Record error metric
                        duration = time.time() - start_time
                        sentry_sdk.set_measurement("duration", duration, "second")
                        sentry_sdk.set_tag("status", "error")
                        sentry_sdk.set_extra("error_type", type(exc).__name__)
                        
                        sentry_sdk.capture_exception(exc)
                        raise
            
            return wrapper
        return decorator
    
    def track_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Track custom business metrics in Sentry.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            tags: Additional tags for the metric
            
        Example:
            sentry_monitor.track_metric("samples_processed", 150, {"batch_id": "batch_001"})
        """
        with sentry_sdk.start_span(op="metric", description=metric_name) as span:
            span.set_measurement(metric_name, value)
            if tags:
                for key, val in tags.items():
                    span.set_tag(key, val)
    
    def add_breadcrumb(self, message: str, category: str = "custom", level: str = "info", data: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a breadcrumb for debugging context.
        
        Args:
            message: Breadcrumb message
            category: Category of the breadcrumb
            level: Level (debug, info, warning, error)
            data: Additional data
            
        Example:
            sentry_monitor.add_breadcrumb("Starting data processing", "process", "info", {"batch_size": 100})
        """
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data
        )
    
    def set_context(self, key: str, context: Dict[str, Any]) -> None:
        """
        Set context information for the current scope.
        
        Args:
            key: Context key
            context: Context data
            
        Example:
            sentry_monitor.set_context("processing_results", {
                "total_configs": 10,
                "successful": 8,
                "failed": 2
            })
        """
        sentry_sdk.set_context(key, context)
    
    def set_tag(self, key: str, value: str) -> None:
        """
        Set a tag for the current scope.
        
        Args:
            key: Tag key
            value: Tag value
            
        Example:
            sentry_monitor.set_tag("workspace", "my-terra-workspace")
        """
        sentry_sdk.set_tag(key, value)
    
    def capture_message(self, message: str, level: str = "info") -> None:
        """
        Manually capture a message.
        
        Args:
            message: Message to capture
            level: Level (debug, info, warning, error, fatal)
            
        Example:
            sentry_monitor.capture_message("Processing completed successfully", "info")
        """
        sentry_sdk.capture_message(message, level)



def init_sentry(
    dsn: Optional[str] = None,
    service_name: str = "bioforklift-service",
    project_name: str = "bioforklift",
    **kwargs
) -> SentryMonitor:
    """
    Quick initialization of Sentry monitoring.
    
    Args:
        dsn: Sentry DSN
        service_name: Service name for tagging
        **kwargs: Additional arguments for SentryMonitor
    
    Returns:
        Configured SentryMonitor instance
        
    Example:
        from bioforklift.alerting.sentry import init_sentry
        
        sentry_monitor = init_sentry(
            dsn="your-sentry-dsn",
            service_name="my-terra-script"
        )
        
        @sentry_monitor.monitor("data_processing")
        def process_data():
            # Your code here
            pass
    """
    return SentryMonitor(dsn=dsn, service_name=service_name, project_name=project_name, **kwargs)