from pydantic import BaseModel, Field, computed_field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class WorkflowConfig(BaseModel):
    """Model for Terra workflow submission configuration"""

    methodConfigurationNamespace: str
    methodConfigurationName: str
    entityType: str
    entityName: str
    expression: Optional[str] = None
    useCallCache: bool = True
    deleteIntermediateOutputFiles: bool = True
    useReferenceDisks: bool = True
    memoryRetryMultiplier: float = 1.0
    workflowFailureMode: str = "NoNewCalls"
    userComment: Optional[str] = None
    ignoreEmptyOutputs: bool = False


class WorkflowMetadata(BaseModel):
    """Model for workflow metadata"""

    workflow_id: str
    status: str
    submission_id: str
    entity_name: Optional[str] = None
    submission_date: Optional[datetime] = None
    upload_source: Optional[str] = None


class SubmissionInfo(BaseModel):
    """Model for submission information"""

    submission_id: str
    entity_name: str
    submission_date: datetime
    status: Optional[str] = None


class TransferStatus(str, Enum):
    """Status codes for sample transfer operations"""

    SUCCESS = "success"
    NO_NEW_SAMPLES = "no_new_samples"
    ERROR = "error"
    PARTIAL_SUCCESS = "partial_success"


class TransferResult(BaseModel):
    """Model for sample transfer operation results"""

    status: TransferStatus
    transferred_ids: List[str] = Field(default_factory=list)
    skipped_ids: List[str] = Field(default_factory=list)
    failed_ids: List[str] = Field(default_factory=list)
    message: Optional[str] = None

    @computed_field
    @property
    def transferred_count(self) -> int:
        return len(self.transferred_ids)

    @computed_field
    @property
    def skipped_count(self) -> int:
        return len(self.skipped_ids)

    @computed_field
    @property
    def failed_count(self) -> int:
        return len(self.failed_ids)
