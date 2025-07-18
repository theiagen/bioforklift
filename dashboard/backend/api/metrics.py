from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from models.monitoring import (
    DailyRunSummary,
    WorkflowStateDistribution,
    ConfigurationMetrics,
    RecentFailure,
    ProcessingTimeTrend,
    ActiveConfiguration,
    SystemHealthMetrics,
    DashboardMetrics,
    ErrorResponse
)
from typing import Union
from services.bigquery_service import BigQueryService
from services.mock_data_service import MockDataService
from fastapi import Depends
from auth.oauth import get_current_user, get_user_credentials, is_development_mode
from google.cloud import bigquery

logger = logging.getLogger(__name__)

router = APIRouter()

def get_data_service():
    """Get the global data service instance"""
    from main import get_data_service as _get_service
    return _get_service()


@router.get("/daily-runs", response_model=List[DailyRunSummary])
async def get_daily_runs(
    days_back: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get daily runs summary for the specified number of days"""
    try:
        data = service.get_daily_runs_summary(days_back)
        return [DailyRunSummary(**row) for row in data]
    except Exception as e:
        logger.error(f"Error fetching daily runs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch daily runs data")


@router.get("/workflow-states", response_model=WorkflowStateDistribution)
async def get_workflow_states(
    days_back: int = Query(default=7, ge=1, le=365, description="Number of days to look back"),
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get workflow states distribution for the specified period"""
    try:
        data = service.get_workflow_states_distribution(days_back)
        return WorkflowStateDistribution(workflow_states=data)
    except Exception as e:
        logger.error(f"Error fetching workflow states: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch workflow states data")


@router.get("/configurations", response_model=List[ConfigurationMetrics])
async def get_configuration_metrics(
    days_back: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get metrics by configuration for the specified period"""
    try:
        data = service.get_configuration_metrics(days_back)
        return [ConfigurationMetrics(**row) for row in data]
    except Exception as e:
        logger.error(f"Error fetching configuration metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch configuration metrics")


@router.get("/recent-failures", response_model=List[RecentFailure])
async def get_recent_failures(
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of failures to return"),
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get recent failed workflows for debugging"""
    try:
        data = service.get_recent_failures(limit)
        return [RecentFailure(**row) for row in data]
    except Exception as e:
        logger.error(f"Error fetching recent failures: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recent failures")


@router.get("/processing-times", response_model=List[ProcessingTimeTrend])
async def get_processing_time_trends(
    days_back: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get processing time trends over the specified period"""
    try:
        data = service.get_processing_time_trends(days_back)
        return [ProcessingTimeTrend(**row) for row in data]
    except Exception as e:
        logger.error(f"Error fetching processing time trends: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch processing time trends")


@router.get("/active-configurations", response_model=List[ActiveConfiguration])
async def get_active_configurations(
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get list of active configurations"""
    try:
        data = service.get_active_configurations()
        return [ActiveConfiguration(**row) for row in data]
    except Exception as e:
        logger.error(f"Error fetching active configurations: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch active configurations")


@router.get("/system-health", response_model=SystemHealthMetrics)
async def get_system_health(
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Get overall system health metrics"""
    try:
        data = service.get_system_health_metrics()
        return SystemHealthMetrics(**data)
    except Exception as e:
        logger.error(f"Error fetching system health: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch system health metrics")


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    days_back: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service),
    user: dict = Depends(get_current_user)
):
    """Get all dashboard metrics in a single request"""
    try:
        # Fetch all metrics in parallel could be added here for better performance
        daily_runs_data = service.get_daily_runs_summary(days_back)
        workflow_states_data = service.get_workflow_states_distribution(min(days_back, 7))
        config_metrics_data = service.get_configuration_metrics(days_back)
        recent_failures_data = service.get_recent_failures(20)
        processing_trends_data = service.get_processing_time_trends(days_back)
        active_configs_data = service.get_active_configurations()
        system_health_data = service.get_system_health_metrics()
        
        return DashboardMetrics(
            daily_runs=[DailyRunSummary(**row) for row in daily_runs_data],
            workflow_distribution=WorkflowStateDistribution(workflow_states=workflow_states_data),
            configuration_metrics=[ConfigurationMetrics(**row) for row in config_metrics_data],
            recent_failures=[RecentFailure(**row) for row in recent_failures_data],
            processing_trends=[ProcessingTimeTrend(**row) for row in processing_trends_data],
            active_configurations=[ActiveConfiguration(**row) for row in active_configs_data],
            system_health=SystemHealthMetrics(**system_health_data)
        )
    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard metrics")


@router.post("/cache/clear")
async def clear_cache(
    service: Union[BigQueryService, MockDataService] = Depends(get_data_service)
):
    """Clear the BigQuery service cache"""
    try:
        if hasattr(service, 'clear_cache'):
            service.clear_cache()
        else:
            logger.info("Cache clear not supported for current service type")
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")