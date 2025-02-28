from typing import Dict, Any, List
from datetime import datetime
from .models import WorkflowConfig, WorkflowMetadata, SubmissionInfo
from .client import TerraClient


class TerraSubmissions:
    """Class meant to handle Terra workflow/submissions"""

    def __init__(self, client: TerraClient):
        self.client = client

    def submit_workflow(
        self,
        config: WorkflowConfig,
        use_destination: bool = True,
    ) -> Dict[str, Any]:
        """
        Submit a workflow for execution

        Args:
            config: WorkflowConfig containing all workflow configuration
            use_destination: Whether to use destination workspace (True) or source workspace

        Returns:
            Dict containing submission response
        """
        return self.client.post(
            "submissions",
            data=config.model_dump(exclude_none=True),
            use_destination=use_destination,
        ).json()

    def get_submission_status(
        self,
        submission_id: str,
        use_destination: bool = True,
    ) -> Dict[str, Any]:
        """
        Get status of a workflow submission

        Args:
            submission_id: ID of the submission to check
            use_destination: Whether to use destination workspace (True) or source workspace
        """
        return self.client.get(
            f"submissions/{submission_id}", use_destination=use_destination
        ).json()

    def get_all_submissions(
        self,
        skip_aborted: bool = True,
        use_destination: bool = True,
    ) -> List[SubmissionInfo]:
        """
        Get all submissions from workspace

        Args:
            skip_aborted: Whether to skip aborted submissions
            use_destination: Whether to use destination workspace (True) or source workspace (False)

        Returns:
            List of submission information
        """
        response = self.client.get("submissions").json()
        submissions = []

        for submission in response:
            # Skip aborted submissions if requested
            if skip_aborted and submission.get("status") == "Aborted":
                continue

            if (
                "submissionEntity" in submission
                and "entityName" in submission["submissionEntity"]
            ):
                submissions.append(
                    SubmissionInfo(
                        submission_id=submission["submissionId"],
                        entity_name=submission["submissionEntity"]["entityName"],
                        submission_date=datetime.fromisoformat(
                            submission["submissionDate"].rstrip("Z")
                        ),
                        status=submission.get("status"),
                    )
                )

        return submissions

    def get_workflows_by_submission(
        self,
        submission_id: str,
        skip_aborted: bool = True,
        use_destination: bool = False,
    ) -> List[WorkflowMetadata]:
        """
        Get all workflows for a submission

        Args:
            submission_id: ID of the submission
            skip_aborted: Whether to skip aborted workflows
            use_destination: Whether to use destination workspace (True) or source workspace (False)

        Returns:
            List of workflow metadata
        """
        response = self.client.get(
            f"submissions/{submission_id}", use_destination=use_destination
        ).json()
        workflows = []

        submission_entity = response.get("submissionEntity", {})
        submission_date = datetime.fromisoformat(response["submissionDate"].rstrip("Z"))

        for workflow in response.get("workflows", []):
            if skip_aborted and workflow.get("status") == "Aborted":
                continue

            if (
                "workflowEntity" in workflow
                and "entityName" in workflow["workflowEntity"]
            ):
                workflows.append(
                    WorkflowMetadata(
                        workflow_id=workflow["workflowId"],
                        status=workflow.get("status", "Unknown"),
                        submission_id=submission_id,
                        entity_name=workflow["workflowEntity"]["entityName"],
                        submission_date=submission_date,
                        upload_source=submission_entity.get("entityName"),
                    )
                )

        return workflows

    def get_workflows_by_entity(
        self,
        entity_names: List[str],
        skip_aborted: bool = True,
        use_destination: bool = False,
    ) -> Dict[str, WorkflowMetadata]:
        """
        Get workflow metadata for specific entities

        Args:
            entity_names: List of entity names to look up
            skip_aborted: Whether to skip aborted workflows
            use_destination: Whether to use destination workspace (True) or source workspace (False)

        Returns:
            Dict mapping entity names to their workflow metadata
        """
        submissions = self.get_all_submissions(
            skip_aborted=skip_aborted, use_destination=use_destination
        )
        workflow_dict = {}

        for submission in submissions:
            workflows = self.get_workflows_by_submission(
                submission.submission_id, skip_aborted=skip_aborted
            )

            for workflow in workflows:
                if workflow.entity_name in entity_names:
                    workflow_dict[workflow.entity_name] = workflow

        return workflow_dict
