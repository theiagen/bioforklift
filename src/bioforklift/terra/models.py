from pydantic import BaseModel, Field, model_validator, computed_field
from datetime import datetime
from typing import Optional, Dict, List, Any
from typing_extensions import Self
from enum import Enum
import json

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


class MethodRepoMethod(BaseModel):
    """
    Model for method repository method.
    """
    methodUri: Optional[str] = None
    sourceRepo: Optional[str] = None
    methodPath: Optional[str] = None
    methodVersion: Optional[str] = None

    @model_validator(mode="after")
    def check_required_fields(self) -> Self:
        # Note: having all four fields is perfectly valid, but not required
        if self.methodUri is None and not all([self.sourceRepo, self.methodPath, self.methodVersion]):
            raise ValueError("Either 'methodUri' or all of 'sourceRepo', 'methodPath', and 'methodVersion' must be provided.")
        return self


class MethodConfig(BaseModel):
    """
    Model for workspace method configuration.
    See https://api.firecloud.org/#/Method%20Configurations/getWorkspaceMethodConfig
    """

    namespace: str
    name: str
    rootEntityType: str
    deleted: bool = False
    prerequisites: Dict[str, Any] = Field(default_factory=dict)
    methodRepoMethod: MethodRepoMethod = Field(default_factory=MethodRepoMethod)
    methodConfigVersion: int = 0
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)

    # Pydandic model method runs right after initialization
    def model_post_init(self, __context: dict) -> None:
        # Automatically JSON-encode input values for Terra API compatibility
        # Skip values that contain Terra workspace references (this.*)
        self.inputs = {
            k: v if isinstance(v, str) and v.startswith("this.") else json.dumps(v)
            for k, v in self.inputs.items()
        }
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
