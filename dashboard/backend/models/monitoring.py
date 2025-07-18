from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, date


class DailyRunSummary(BaseModel):
    """Daily run summary model"""
    date: date
    total_runs: int = Field(ge=0)
    successful_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    aborted_runs: int = Field(ge=0)
    in_progress_runs: int = Field(ge=0)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_runs == 0:
            return 0.0
        return round((self.successful_runs / self.total_runs) * 100, 2)


class WorkflowStateDistribution(BaseModel):
    """Workflow state distribution model"""
    workflow_states: Dict[str, int]
    
    @property
    def total_workflows(self) -> int:
        """Total number of workflows"""
        return sum(self.workflow_states.values())


class ConfigurationMetrics(BaseModel):
    """Configuration metrics model"""
    config_id: str
    config_name: Optional[str] = None
    total_samples: int = Field(ge=0)
    successful_samples: int = Field(ge=0)
    failed_samples: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=100.0)
    avg_processing_time_minutes: Optional[float] = None


class RecentFailure(BaseModel):
    """Recent failure model"""
    entity_identifier: str
    config_id: Optional[str] = None
    config_name: Optional[str] = None
    workflow_state: str
    created_at: datetime
    submitted_at: Optional[datetime] = None
    terra_submission_id: Optional[str] = None
    terra_workflow_id: Optional[str] = None


class ProcessingTimeTrend(BaseModel):
    """Processing time trend model"""
    date: date
    avg_processing_time_minutes: Optional[float] = None
    sample_count: int = Field(ge=0)


class ActiveConfiguration(BaseModel):
    """Active configuration model"""
    id: str
    name: str
    state: str
    prefix: str
    terra_analysis_method: str
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class SystemHealthMetrics(BaseModel):
    """System health metrics model"""
    total_samples: int = Field(ge=0)
    samples_last_24h: int = Field(ge=0)
    successful_last_24h: int = Field(ge=0)
    failed_last_24h: int = Field(ge=0)
    currently_in_progress: int = Field(ge=0)
    success_rate_24h: float = Field(ge=0.0, le=100.0)
    failure_rate_24h: float = Field(ge=0.0, le=100.0)


class DashboardMetrics(BaseModel):
    """Complete dashboard metrics model"""
    daily_runs: List[DailyRunSummary]
    workflow_distribution: WorkflowStateDistribution
    configuration_metrics: List[ConfigurationMetrics]
    recent_failures: List[RecentFailure]
    processing_trends: List[ProcessingTimeTrend]
    active_configurations: List[ActiveConfiguration]
    system_health: SystemHealthMetrics


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)