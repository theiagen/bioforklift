from pydantic import BaseModel, Field, model_validator, computed_field, field_serializer
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
    methodRepoMethod: MethodRepoMethod
    deleted: bool = False
    prerequisites: Dict[str, Any] = Field(default_factory=dict)
    methodConfigVersion: int = 0
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer("inputs")
    def serialize_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        JSON-encode input values for Terra API compatibility.
        Terra workspace references (this.*) are kept as-is.

        This runs only during serialization (model_dump), not construction,
        preventing double-encoding when round-tripping configs through the API.
        """
        return {
            k: self._encode_value(v)
            for k, v in inputs.items()
        }

    @staticmethod
    def _encode_value(value: Any) -> str:
        """Encode a single input value for Terra API."""
        # Keep Terra workspace references as-is
        if isinstance(value, str) and value.startswith("this."):
            return value

        # If it's already a JSON-encoded string, return as-is
        if isinstance(value, str):
            try:
                json.loads(value)
                return value  # Valid JSON, don't re-encode
            except json.JSONDecodeError:
                pass  # Not valid JSON, encode it

        return json.dumps(value)


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
