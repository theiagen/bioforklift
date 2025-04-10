from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


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
