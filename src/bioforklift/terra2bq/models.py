from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class OperationStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    NO_DATA = "no_data"
    NO_NEW_SAMPLES = "no_new_samples"
    PARTIAL_SUCCESS = "partial_success"
    NO_TERRA_DATA = "no_terra_data"
    NO_UPDATES = "no_updates"
    NO_CONFIGS = "no_configs"
    NO_DATA_AFTER_CLEANUP = "no_data_after_cleanup"


class BaseResult(BaseModel):
    status: OperationStatus
    message: Optional[str] = None
    config_id: Optional[str] = None


class CountResult(BaseResult):
    loaded_count: Optional[int] = Field(default=0, ge=0)
    uploaded_count: Optional[int] = Field(default=0, ge=0)
    filtered_count: Optional[int] = Field(default=0, ge=0)
    updated_count: Optional[int] = Field(default=0, ge=0)


class ConfigProcessingResult(CountResult):
    workflow_count: Optional[int] = Field(default=0, ge=0)
    set_name: Optional[str] = None
    submission_id: Optional[str] = None


class WorkflowResult(BaseResult):
    submission_id: Optional[str] = None
    workflow_count: Optional[int] = Field(default=0, ge=0)
    workflow_states: Optional[Dict[str, int]] = Field(default_factory=dict)
    failed_updates: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class MetadataSyncResult(BaseResult):
    bq_updated_count: Optional[int] = Field(default=0, ge=0)
    destination_updated_count: Optional[int] = Field(default=0, ge=0)
    total_updated_count: Optional[int] = Field(default=0, ge=0)
    processed_configs: Optional[int] = Field(default=0, ge=0)
    failed_updates: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    updated_entities: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DataResult(BaseResult):
    data: Optional[Any] = None
    error: Optional[str] = None

    @model_validator(mode='after')
    def validate_status_with_data(self):
        if self.status == OperationStatus.SUCCESS and self.data is None:
            raise ValueError('data must be provided when status is success')
        return self


class UploadResult(CountResult):
    set_name: Optional[str] = None


class DownloadResult(CountResult):
    pass


class SubmissionResult(WorkflowResult):
    pass


class ProcessAllConfigsResult(BaseResult):
    results: List[ConfigProcessingResult] = Field(default_factory=list)
    total_configs: int = Field(default=0, ge=0)
    successful_configs: int = Field(default=0, ge=0)
    failed_configs: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def validate_config_counts(self):
        if self.successful_configs > self.total_configs:
            raise ValueError('successful_configs cannot exceed total_configs')
        if self.failed_configs > self.total_configs:
            raise ValueError('failed_configs cannot exceed total_configs')
        return self