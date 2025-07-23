# Sentry Error Monitoring Setup

bioforklift includes built-in Sentry integration for comprehensive error tracking and performance monitoring.

## Prerequisites

1. A Sentry account and project
2. Sentry DSN (Data Source Name) from your project settings

## Configuration

### Basic Setup

Set up Sentry monitoring in your scripts:

```python
from bioforklift.alerting import init_sentry

# Initialize Sentry monitoring
sentry_monitor = init_sentry(
    dsn="your-sentry-dsn-here",
    service_name="your-service-name"
)
```

### Environment Variables

For production deployments, use environment variables:

```bash
export SENTRY_DSN="your-sentry-dsn-here"
export ENVIRONMENT="production"  # Optional: defaults to 'production'
```

Then initialize without parameters:

```python
sentry_monitor = init_sentry(service_name="your-service-name")
```

## Usage Examples

### Function Monitoring

Use the `@monitor` decorator to automatically track function execution:

```python
@sentry_monitor.monitor("data_processing")
def process_terra_data():
    # Your processing logic here
    pass

# With custom options
@sentry_monitor.monitor(
    operation_name="terra_sync",
    track_performance=True,
    capture_args=False  # Set to True to capture function arguments
)
def sync_data_to_bigquery():
    # Your sync logic here
    pass
```

### Manual Error Capture

Capture specific errors or messages:

```python
try:
    # Your code here
    result = risky_operation()
except Exception as e:
    sentry_monitor.capture_message(f"Operation failed: {str(e)}", "error")
    raise
```

### Adding Context and Tags

Enhance error reports with additional context:

```python
# Set tags for categorization
sentry_monitor.set_tag("workspace", "my-terra-workspace")
sentry_monitor.set_tag("batch_id", "batch_001")

# Add structured context
sentry_monitor.set_context("processing_info", {
    "total_samples": 150,
    "successful": 140,
    "failed": 10
})

# Add breadcrumbs for debugging
sentry_monitor.add_breadcrumb(
    "Starting data validation", 
    "process", 
    "info", 
    {"validator": "schema_v1"}
)
```

### Custom Metrics

Track business metrics:

```python
# Track sample processing metrics
sentry_monitor.track_metric("samples_processed", 150, {"batch_id": "batch_001"})
sentry_monitor.track_metric("processing_duration", 45.2, {"unit": "seconds"})
```

## Advanced Configuration

### Custom SentryMonitor Instance

For more control, create a custom `SentryMonitor` instance:

```python
from bioforklift.alerting.sentry import SentryMonitor

sentry_monitor = SentryMonitor(
    dsn="your-sentry-dsn-here",
    service_name="bioforklift-pipeline",
    traces_sample_rate=0.1,  # Sample 10% of transactions for performance
    release="1.2.0",
    environment="staging",
    custom_tags={
        "team": "bioinformatics",
        "pipeline": "covid-analysis"
    }
)
```

### Cloud Run Integration

For Google Cloud Run deployments, Sentry automatically captures:
- Project ID (`GOOGLE_CLOUD_PROJECT`)

These are included as tags in all error reports.

## Monitoring Best Practices

1. **Use descriptive operation names** in the `@monitor` decorator
2. **Set meaningful tags** to categorize and filter errors
3. **Add context** before operations that might fail
4. **Use breadcrumbs** to track the execution flow
5. **Track custom metrics** for business intelligence
6. **Don't capture sensitive data** in arguments or context

## Complete Example

Here's a complete example based on the bioforklift CLI structure:

```python
import click
from pathlib import Path
from bioforklift.terra2bq import Terra2BQ
from bioforklift.terra2bq.models import OperationStatus
from bioforklift.alerting import init_sentry

# Initialize Sentry monitoring
sentry_monitor = init_sentry(
    dsn="your-sentry-dsn-here",
    service_name="bioforklift-analysis-cli"
)

@click.group()
@click.option('--project', help='BigQuery project ID')
@click.option('--dataset', help='BigQuery dataset name')
@click.option('--samples-table', help='Samples table name')
@click.option('--configs-table', help='Configs table name')
@click.pass_context
def cli(ctx, project, dataset, samples_table, configs_table):
    """Bioforklift CLI tool for managing Terra data in BigQuery."""
    ctx.ensure_object(dict)
    ctx.obj['terra2bq'] = Terra2BQ(
        bigquery_project=project,
        bigquery_dataset=dataset,
        samples_table=samples_table,
        configs_table=configs_table,
    )

@cli.command()
@click.pass_context
@sentry_monitor.monitor("sample_automation")
def sample_automation(ctx):
    """Process configurations with comprehensive Sentry monitoring"""
    # Set tag for categorization
    sentry_monitor.set_tag("operation", "sample_automation")
    
    # Add breadcrumb for debugging
    sentry_monitor.add_breadcrumb(
        "Starting sample automation processing",
        category="process",
        level="info"
    )
    
    terra2bq = ctx.obj['terra2bq']
    
    click.echo("Running sample automation processing...")
    results = terra2bq.process_all_configs()
    
    success_count = sum(1 for r in results if r.status == OperationStatus.SUCCESS)
    failure_count = len(results) - success_count
    
    # Alert if there are any failures
    if failure_count > 0:
        sentry_monitor.capture_message(
            f"Sample automation failures: {failure_count} of {len(results)} configs failed", 
            level="error"
        )
    
    # Track business metrics
    sentry_monitor.track_metric("configs_processed", len(results))
    sentry_monitor.track_metric("configs_successful", success_count)
    sentry_monitor.track_metric("configs_failed", failure_count)
    
    if len(results) > 0:
        success_rate = success_count / len(results)
        sentry_monitor.track_metric("success_rate", success_rate)
        
        # Set context for this transaction
        sentry_monitor.set_context("results", {
            "total_configs": len(results),
            "successful": success_count,
            "failed": failure_count,
            "success_rate": success_rate
        })
    
    # Add breadcrumb for completion
    sentry_monitor.add_breadcrumb(
        f"Completed processing {len(results)} configurations",
        category="process",
        level="info",
        data={"success_count": success_count, "failure_count": failure_count}
    )
    
    click.echo(f"Completed processing configurations ({success_count} successful)")

@cli.command()  
@click.option('--days-back', default=1, type=int, help='Number of days to look back')
@click.pass_context
def workflow_status_update(ctx, days_back):
    """Update workflow status from Terra with error monitoring"""
    terra2bq = ctx.obj['terra2bq']
    
    update_results = terra2bq.update_workflow_status(days_back=days_back)
    
    # Alert on workflow status update failures
    if hasattr(update_results, 'status') and update_results.status == OperationStatus.ERROR:
        sentry_monitor.capture_message("Workflow status update failed", level="error")

@cli.command()
@click.option('--days-back', default=1, type=int, help='Number of days to look back')
@click.pass_context
def sync_metadata(ctx, days_back):
    """Sync metadata from Terra to BigQuery with monitoring"""
    terra2bq = ctx.obj['terra2bq']
    
    sync_results = terra2bq.sync_metadata(days_back=days_back)
    
    # Alert on metadata sync failures
    if hasattr(sync_results, 'status') and sync_results.status == OperationStatus.ERROR:
        sentry_monitor.capture_message("Metadata sync failed", level="error")

if __name__ == '__main__':
    cli()
```

This example demonstrates:

- **Initialization**: Setting up Sentry with DSN and service name
- **Function Monitoring**: Using the `@monitor` decorator on CLI commands
- **Tags and Context**: Setting operation tags and structured context data
- **Breadcrumbs**: Adding debugging breadcrumbs at key processing points
- **Custom Metrics**: Tracking business metrics like success rates and processing counts
- **Error Alerting**: Capturing specific error conditions with appropriate severity levels
- **Performance Tracking**: Automatic transaction tracking for decorated functions

This provides comprehensive monitoring with automatic error capture, performance tracking, and custom business metrics for your bioforklift pipelines.