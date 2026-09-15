from typing import Dict, Any, List
from datetime import datetime
from .models import WorkflowConfig, WorkflowMetadata, SubmissionInfo
from .client import TerraClient
from bioforklift.forklift_logging import setup_logger

logger = setup_logger("terra_submissions.py")


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

        logger.info(f"Submitting workflow with config:")
        for key, value in config.model_dump().items():
            logger.info(f"{key}: {value}")

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
        logger.info(f"Fetching status for submission ID: {submission_id}")
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
        logger.info("Fetching all submissions")
        response = self.client.get("submissions").json()
        submissions = []

        for submission in response:
            # Skip aborted submissions if requested
            if skip_aborted and submission.get("status") == "Aborted":
                logger.info(
                    f"Skipping aborted submission: {submission['submissionId']}"
                )
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
        logger.info(f"Fetched {len(submissions)} submissions")
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
        logger.info(f"Fetching workflows for submission ID: {submission_id}")
        response = self.client.get(
            f"submissions/{submission_id}", use_destination=use_destination
        ).json()
        logger.info(f"Workflows within {submission_id} fetched.")
        workflows = []
        submission_entity = response.get("submissionEntity", {})
        submission_date = datetime.fromisoformat(response["submissionDate"].rstrip("Z"))

        for workflow in response.get("workflows", []):
            if "workflowId" not in workflow:
                logger.info(
                    f"Skipping workflow with missing workflowId in submission {submission_id}"
                )
                continue

            if skip_aborted and workflow.get("status") == "Aborted":
                logger.info(f"Skipping aborted workflow: {workflow['workflowId']}")
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
        logger.info(f"Fetched {len(workflows)} workflows")
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
