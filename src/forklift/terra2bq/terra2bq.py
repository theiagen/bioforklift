import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd
import pytz
from forklift.bigquery import BigQuery
from forklift.terra import Terra
from forklift.bigquery.utils import drop_system_value_columns
from forklift.terra.models import WorkflowConfig

logger = logging.getLogger(__name__)


class Terra2BQ:
    """
    Integration layer for Terra and BigQuery operations.
    
    This class provides methods to:
    1. Download data from Terra
    2. Load it into BigQuery
    3. Upload processed data back to Terra
    4. Create and manage Terra entity sets
    5. Submit and monitor Terra workflows
    6. Update BigQuery records with Terra submission status
    """

    def __init__(
        self,
        bigquery_project: str,
        bigquery_dataset: str,
        bigquery_location: str = "us-central1",
        google_credentials_json: Optional[Path] = None,
        samples_table: str = "samples",
        configs_table: str = "configs",
        lookup_timeframe: str = "today",
        lookup_days_back: Optional[int] = None,
        lookup_hours_back: Optional[int] = None,
        samples_schema_yaml: Optional[Path] = None,
        configs_schema_yaml: Optional[Path] = None,
        source_workspace: Optional[str] = None,
        source_project: Optional[str] = None,
        source_datatable: Optional[str] = None,
        destination_workspace: Optional[str] = None,
        destination_project: Optional[str] = None,
        destination_datatable: Optional[str] = None,
        project_timezone = "UTC",
        bigquery_upload_df: Optional[pd.DataFrame] = None,
        metadata_cleanup_fn: Optional[callable] = None,
    ):
        """
        Initialize Terra2BQ with BigQuery and Terra information.
        
        Args:
            bigquery_project: GCP project ID for BigQuery
            bigquery_dataset: BigQuery dataset name
            bigquery_location: BigQuery dataset location
            google_credentials_json: Optional service account credentials dict for BigQuery
            samples_table: Name of the samples table in BigQuery
            configs_table: Name of the configs table in BigQuery
            lookup_timeframe: Default timeframe for sample lookup (default: "today", options: "today", "yesterday", "week", "month", "custom")
            lookup_days_back: Number of days to look back for custom timeframe (this must be provided or lookup_hours_back if lookup_timeframe is "custom")
            lookup_hours_back: Number of hours to look back for custom timeframe (this must be provided or lookup_days_back if lookup_timeframe is "custom")
            samples_schema_yaml: Path to samples schema YAML file
            configs_schema_yaml: Path to configs schema YAML file
            source_workspace: Default source workspace for Terra, if not provided in configuration
            source_project: Default source project for Terra, if not provided in configuration
            source_datatable: Source data table for Terra, if not provided in configuration
            destination_workspace: Destination workspace for Terra, if not provided in configuration
            destination_project:  Destination project for Terra, if not provided in configuration
            destination_datatable: Destination data table for Terra, if not provided in configuration
            destination_datatable: Destination data table for Terra, if not provided in configuration
            project_timezone: Timezone for the project
            bigquery_upload_df: Optional DataFrame to use for BigQuery upload, would bypass download from Terra
            metadata_cleanup_fn: Optional function to clean up metadata before upload to BigQuery
        """
        
        # Set up credentials if provided
        self.google_credentials_json = google_credentials_json
        
        # Initialize bigquery client
        self.bigquery = BigQuery(
            project=bigquery_project,
            dataset=bigquery_dataset,
            credentials=self.google_credentials_json,
            location=bigquery_location,
        )
        
        # Store lookup timeframe and days/hours back
        self.lookup_timeframe = lookup_timeframe
        self.lookup_days_back = lookup_days_back
        self.lookup_hours_back = lookup_hours_back
        if self.lookup_timeframe == "custom" and not (self.lookup_days_back or self.lookup_hours_back):
            raise ValueError("Custom lookup timeframe requires lookup_days_back or lookup_hours_back")
        
        # Store table names and schema paths
        self.samples_table = samples_table
        self.configs_table = configs_table
        self.samples_schema_yaml = samples_schema_yaml
        self.configs_schema_yaml = configs_schema_yaml
        
        # Initialize operation instances to None
        self.samples_ops = None
        self.config_ops = None
        self.terra = None
        
        # Store Terra workspace/project information, if provided, otherwise will take from config
        self.source_workspace = source_workspace
        self.source_project = source_project
        self.source_datatable = source_datatable
        self.destination_workspace = destination_workspace
        self.destination_project = destination_project
        self.destination_datatable = destination_datatable
        
        # Store project timezone, default to UTC
        self.project_timezone = project_timezone
        
        # Store DataFrame for upload if provided
        self.bigquery_upload_df = bigquery_upload_df
        
        # Metadata cleanup function via dependency injection
        self.metadata_cleanup_fn = metadata_cleanup_fn
        
        # Initialize operations objects
        self.initialize_operations()
        
    def _get_target_entity_from_config(self, config: Dict[str, Any]) -> str:
        """
        Get the target entity name from a configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Target entity name
        """
        target_entity = config.get("terra_method_config", {}).get("entityType")
        if not target_entity:
            raise ValueError(f"Configuration {config.get('id')} is missing terra_entity_type field")
        
        target_entity_clean = target_entity.replace("_set", "")
        
        return target_entity_clean

    def initialize_operations(self) -> None:
        """Initialize BigQuery operations objects if not already initialized."""
        # Helper function to get the expected operation classes
        if not self.samples_ops and self.samples_schema_yaml:
            self.samples_ops = self.bigquery.get_sample_operations(
                table_name=self.samples_table,
                sample_schema_yaml=self.samples_schema_yaml
            )
            
        if not self.config_ops and self.configs_schema_yaml:
            self.config_ops = self.bigquery.get_config_operations(
                table_name=self.configs_table,
                config_schema_yaml=self.configs_schema_yaml
            )

    def setup_terra_client(
        self, 
        config: Dict[str, Any]
    ) -> None:
        """
        Set up Terra client based on a configuration.
        
        Args:
            config: Configuration dictionary containing Terra workspace and project details
        """
        # Order of precedence for Terra workspace/project:
        # 1. Values passed in constructor
        # 2. Values from config dictionary
        # 3. Raise error if neither is available
        
        source_workspace = self.source_workspace
        if not source_workspace:
            source_workspace = config.get("terra_source_workspace")
            if not source_workspace:
                raise ValueError(f"No source workspace provided for configuration {config.get('id')}")
        
        source_project = self.source_project
        if not source_project:
            source_project = config.get("terra_source_project")
            if not source_project:
                raise ValueError(f"No source project provided for configuration {config.get('id')}")
        
        # Determine destination workspace/project else fall back to source if not specified
        destination_workspace = self.destination_workspace
        if not destination_workspace:
            destination_workspace = config.get("terra_destination_workspace", source_workspace)
        
        destination_project = self.destination_project
        if not destination_project:
            destination_project = config.get("terra_destination_project", source_project)
        
        # Initialize Terra client
        self.terra = Terra(
            source_workspace=source_workspace,
            source_project=source_project,
            destination_workspace=destination_workspace,
            destination_project=destination_project,
            credentials=self.google_credentials_json
        )
        
        logger.info(
            f"Terra client set up with source: {source_project}/{source_workspace}, "
            f"destination: {destination_project}/{destination_workspace}"
        )

    def get_active_configs(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get active configurations from BigQuery.
        
        Args:
            entity_type: Optional entity type filter
            
        Returns:
            List of active configuration dictionaries
        """
        
        if not self.config_ops:
            raise ValueError("Config operations not initialized. Make sure configs_schema_yaml is provided.")
        
        configs = self.config_ops.get_configs(active_only=True, entity_type=entity_type)
        logger.info(f"Found {len(configs)} active configurations" + 
                   (f" for entity type '{entity_type}'" if entity_type else ""))
        
        return configs
    
    def download_from_terra_to_bigquery(
        self, 
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pull data from source Terra table and load it into BigQuery.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Dictionary with load results and status
        """
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided")
        
        # Set up Terra client for this configuration if not already done
        if not self.terra:
            self.setup_terra_client(config)
        
        # Get entity type from config
        entity_type = config.get("entity_type", self.source_datatable)
        if not entity_type:
            raise ValueError(f"Configuration {config.get('id')} is missing entity_type field")
        
        # Download data from Terra if not provided
        if not self.bigquery_upload_df:
            logger.info(f"Downloading data from Terra entity type: {entity_type}")
            terra_df = self.terra.entities.download_table(entity_type)
        else:
            terra_df = self.bigquery_upload_df
        
        if terra_df.empty:
            logger.warning(f"No data found in Terra table: {entity_type}")
            return {"status": "no_data", "config_id": config.get('id')}
            
        # Apply metadata cleanup function if provided
        if self.metadata_cleanup_fn:
            logger.info("Applying metadata cleanup function to Terra data")
            try:
                original_count = len(terra_df)
                terra_df = self.metadata_cleanup_fn(terra_df)
                logger.info(f"Metadata cleanup: {original_count} rows before, {len(terra_df)} rows after")
                
                if terra_df.empty:
                    logger.warning("All rows were filtered out by the metadata cleanup function")
                    return {"status": "no_data_after_cleanup", "config_id": config.get('id')}
                    
            except Exception as exc:
                logger.error(f"Error in metadata cleanup function: {str(exc)}")
                return {
                    "status": "error", 
                    "message": f"Metadata cleanup error: {str(exc)}",
                    "config_id": config.get('id')
                }
        
        # Load data into BigQuery
        logger.info(f"Loading {len(terra_df)} rows into BigQuery")
        bq_load_result = self.samples_ops.load_dataframe(df=terra_df, config=config)
        
        if not bq_load_result.get("success"):
            logger.error(f"Failed to load data into BigQuery: {bq_load_result.get('errors')}")
            return {
                "status": "error", 
                "message": f"Failed to load data: {bq_load_result.get('errors')}",
                "config_id": config.get("id")
            }
        
        return {
            "status": "success",
            "config_id": config.get("id"),
            "loaded_count": bq_load_result.get("loaded", 0),
            "filtered_count": bq_load_result.get("filtered", 0)
        }
        
    def upload_to_terra(
        self,
        config: Dict[str, Any],
        samples_df: pd.DataFrame,
        upload_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Upload data to Terra destination table and create entity set.
        
        Args:
            config: Configuration dictionary
            samples_df: DataFrame with full sample data including system columns
            upload_df: DataFrame prepared for upload to Terra (system columns removed)
            
        Returns:
            Dictionary with upload results including set name
        """
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided")
        
        # Set up Terra client for this configuration if not already done
        if not self.terra:
            self.setup_terra_client(config)
        
        # Use the target entity from user provided value or configuration
        target_entity = self.destination_datatable
        if not target_entity:
            target_entity = self._get_target_entity_from_config(config)
        logger.info(f"Uploading {len(upload_df)} samples to Terra entity: {target_entity}")
        
        try:
            uploaded_df = self.terra.entities.upload_entities(
                data=upload_df, 
                target=target_entity,
                use_destination=True
            )
        except Exception as e:
            logger.error(f"Failed to upload data to Terra: {str(e)}")
            return {
                "status": "error", 
                "message": f"Failed to upload to Terra: {str(e)}",
                "config_id": config.get("id")
            }
        
        # Create a Set name and create Set in Terra
        current_datetime = datetime.now(pytz.utc)
        
        # Format for database storage (ISO format)
        current_time_str = current_datetime.strftime("%Y-%m-%d %H:%M:%S")

        # Convert to project timezone
        project_timezone = pytz.timezone(self.project_timezone)
        project_datetime = current_datetime.astimezone(project_timezone)
        # Format for set name (compact format)
        current_project_time = project_datetime.strftime("%Y%m%d_%H%M%S")

        # Create set name using the formatted datetime in project timezone
        set_name = f"{config.get('prefix', 'entity_type')}_{current_project_time}"
        
        logger.info(f"Creating entity set in Terra: {set_name}")
        try:
            self.terra.entities.create_entity_set(
                set_name=set_name,
                entity_type=target_entity,
                entities=uploaded_df,
                use_destination=True
            )
        except Exception as e:
            logger.error(f"Failed to create entity set in Terra: {str(e)}")
            return {
                "status": "error", 
                "message": f"Failed to create entity set: {str(e)}",
                "config_id": config.get("id")
            }
        
        # Get IDs from the samples DataFrame
        id_values = samples_df["id"].tolist()
        
        # Create updates for bulk update
        updates = [
            {"id": sample_id, "uploaded_at": current_time_str, "upload_source": set_name}
            for sample_id in id_values
        ]
        
        # Update the records in BigQuery
        logger.info(f"Updating {len(updates)} records in BigQuery with upload status")
        update_result = self.samples_ops.bulk_update_samples(updates)
        
        if update_result.get("failed_updates"):
            logger.warning(
                f"Failed to update {len(update_result['failed_updates'])} records in BigQuery"
            )
        
        # Return success results
        return {
            "status": "success",
            "config_id": config.get("id"),
            "set_name": set_name,
            "uploaded_count": update_result.get("updated_count", 0)
        }
    
    def get_samples_for_submission(
        self,
        config: Dict[str, Any],
        set_name: Optional[str] = None,
        config_id: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get samples from BigQuery that have been uploaded but not yet submitted to a workflow.
        
        Args:
            config: Configuration dictionary
            set_name: Optional specific set name to filter by
            config_id: Optional specific config_id to filter by
            
        Returns:
            DataFrame with samples ready for submission
        """
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided")
        
        # If a specific config_id is not provided, try to get it from the config
        if not config_id and config:
            config_id = config.get("id")
        
        logger.info(f"Retrieving samples for submission" + 
                    (f" from set: {set_name}" if set_name else f" from today"))
        
        # Get samples that have been uploaded but not submitted
        samples_for_submission_df = self.samples_ops.get_samples_by_timeframe(
            timeframe=self.lookup_timeframe,
            days_back=self.lookup_days_back,
            hours_back=self.lookup_hours_back,
            uploaded_filter="uploaded",
            submitted_filter="not_submitted",
            config_id=config_id,
            set_name=set_name
        )
        
        if samples_for_submission_df.empty:
            logger.info("No samples found ready for submission")
        else:
            logger.info(f"Found {len(samples_for_submission_df)} samples ready for submission")
        
        return samples_for_submission_df

    def submit_workflow(
        self,
        config: Dict[str, Any],
        set_name: str,
        samples_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Submit a workflow to Terra for the given set and update tracking info.
        
        Args:
            config: Configuration dictionary
            set_name: Terra entity set name to submit
            
        Returns:
            Dictionary with submission results
        """
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided")
        
        # Set up Terra client for this configuration if not already done
        if not self.terra:
            self.setup_terra_client(config)
        
        # Get workflow configuration details from config
        terra_method_config = config.get("terra_method_config", {})
        
        
        # Make backwards compatible
        if 'userCommentTemplate' in terra_method_config:
            current_datetime = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
            terra_method_config['userComment'] = terra_method_config['userCommentTemplate'].format(date=current_datetime)
            del terra_method_config['userCommentTemplate']
        
        # If it's a string (JSON), parse it
        if isinstance(terra_method_config, str):
            try:
                terra_method_config = json.loads(terra_method_config)
            except json.JSONDecodeError:
                logger.error(f"Invalid terra_method_config JSON in configuration: {config.get('id')}")
                return {
                    "status": "error", 
                    "message": "Invalid terra_method_config JSON",
                    "config_id": config.get("id"),
                    "set_name": set_name
                }
        
        # Prepare workflow configuration
        workflow_config_dict = {
            "methodConfigurationNamespace": terra_method_config.get(
                "methodConfigurationNamespace", 
                config.get("terra_project")
            ),
            "methodConfigurationName": terra_method_config.get(
                "methodConfigurationName", 
                config.get("terra_analysis_method")
            ),
            "entityType": terra_method_config.get("entityType"),
            "entityName": set_name,
            "expression": terra_method_config.get("expression"),
            "useCallCache": terra_method_config.get("useCallCache", True),
            "deleteIntermediateOutputFiles": terra_method_config.get("deleteIntermediateOutputFiles", True),
            "useReferenceDisks": terra_method_config.get("useReferenceDisks", True),
            "memoryRetryMultiplier": terra_method_config.get("memoryRetryMultiplier", 1.0),
            "workflowFailureMode": terra_method_config.get("workflowFailureMode", "NoNewCalls"),
            "userComment": terra_method_config.get(
                "userComment", 
                f"Automated submission from {config.get('name', 'Terra2BQ')}"
            ),
        }
        
        # Create WorkflowConfig object
        workflow_config = WorkflowConfig.model_validate(workflow_config_dict)
        
        # Submit workflow
        logger.info(f"Submitting workflow to Terra for set: {set_name}")
        try:
            submission = self.terra.submissions.submit_workflow(workflow_config, use_destination=True)
            submission_id = submission.get("submissionId")
            
            if not submission_id:
                raise ValueError("Invalid submission response - missing submissionId")
                
            logger.info(f"Workflow submitted successfully with ID: {submission_id}")
            
        except Exception as e:
            logger.error(f"Failed to submit workflow to Terra: {str(e)}")
            return {
                "status": "error", 
                "message": f"Failed to submit workflow: {str(e)}",
                "config_id": config.get("id"),
                "set_name": set_name
            }
        
        # Update BigQuery records with workflow submission information
        entity_names = []
        for workflow in submission.get("workflows", []):
            entity_name = workflow.get("workflowEntity", {}).get("entityName")
            if entity_name:
                entity_names.append(entity_name)
        
        current_time = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        # Create updates for each entity
        workflow_updates = []
        for entity_name in entity_names:
            # Get the BigQuery ID for the entity
            id_value = samples_df["id"].tolist()
            if id_value:
                workflow_updates.append({
                    "id": id,
                    "submitted_at": current_time,
                    "terra_submission_id": submission_id,
                    "workflow_state": "Submitted"
                }
                for id in id_value)
        
        # Update BigQuery with workflow submission information
        if workflow_updates:
            logger.info(f"Updating {len(workflow_updates)} records with workflow submission information")
            workflow_update_result = self.samples_ops.bulk_update_samples(workflow_updates)
            
        if workflow_update_result.get("failed_updates"):
            logger.warning(
                f"Failed to update {len(workflow_update_result['failed_updates'])} records "
                f"with workflow information"
            )
        
        # Return success results
        return {
            "status": "success",
            "config_id": config.get("id"),
            "set_name": set_name,
            "submission_id": submission_id,
            "workflow_count": len(entity_names)
        }
    
    def process_upload_and_submit(
        self, 
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a configuration by uploading data and submitting a workflow.
        This is a wrapper function that handles the sequence:
        1. Get samples from BigQuery that need to be uploaded
        2. Upload to Terra and create a set
        3. Submit workflow for that set
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Dictionary containing results of the operation
        """
        try:
            
            if not self.samples_ops:
                raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided")
            
            # 1. Get samples from BigQuery that need to be uploaded
            logger.info(f"Retrieving samples that need to be uploaded to Terra")
            samples_df = self.samples_ops.get_samples_by_timeframe(
                timeframe=self.lookup_timeframe,
                days_back=self.lookup_days_back,
                hours_back=self.lookup_hours_back,
                uploaded_filter="not_uploaded",
                config_id=config.get("id")
            )
            
            if samples_df.empty:
                logger.info("No samples to upload")
                return {
                    "status": "no_new_samples",
                    "config_id": config.get("id")
                }
            
            # Prepare upload DataFrame by removing system columns
            upload_df = drop_system_value_columns(samples_df, self.samples_schema_yaml)
            logger.info(f"Prepared {len(upload_df)} samples for upload to Terra")
            
            # 2. Upload data to Terra and create entity set
            upload_result = self.upload_to_terra(config, samples_df, upload_df)
            
            if upload_result.get("status") != "success":
                return upload_result
            
            set_name = upload_result.get("set_name")
            if not set_name:
                return {
                    "status": "error",
                    "message": "Upload successful but set_name not returned",
                    "config_id": config.get("id")
                }
            
            # 3. Get latest sample data after upload
            submission_samples = self.get_samples_for_submission(config, set_name=set_name)
            
            if submission_samples.empty:
                return {
                    "status": "error",
                    "message": "No samples found for submission after upload",
                    "config_id": config.get("id"),
                    "set_name": set_name,
                    "uploaded_count": upload_result.get("uploaded_count", 0)
                }
            
            # 4. Submit workflow
            submission_result = self.submit_workflow(config, set_name, submission_samples)
            
            # Combine results
            combined_result = {
                **submission_result,
                "uploaded_count": upload_result.get("uploaded_count", 0)
            }
            
            return combined_result
            
        except Exception as e:
            logger.error(f"Error processing configuration {config.get('id')}: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "config_id": config.get("id")
            }

    def process_configuration(
        self, 
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a single configuration by executing the complete workflow.
        This is a wrapper function that calls the main stages of the workflow.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Dictionary containing results of the operation
        """
        try:
            # 1. Download data from Terra and load into BigQuery
            download_result = self.download_from_terra_to_bigquery(config)
            
            if download_result.get("status") != "success":
                return download_result
            
            # 2. Upload to Terra and submit workflow
            process_result = self.process_upload_and_submit(config)
            
            # Combine results from both steps
            combined_result = {
                **process_result,
                "loaded_count": download_result.get("loaded_count", 0),
                "filtered_count": download_result.get("filtered_count", 0)
            }
            
            return combined_result
            
        except Exception as e:
            logger.error(f"Error processing configuration {config.get('id')}: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "config_id": config.get("id")
            }
    
    def sync_metadata_from_workflows(
        self, 
        days_back: int = 30,
        update_terra: bool = True
    ) -> Dict[str, Any]:
        """
        Sync workflow metadata from Terra to BigQuery and optionally back to Terra.
        
        This method:
        1. Gets samples that have been submitted to Terra in the last X days
        2. Checks Terra for workflow status updates
        3. Updates BigQuery with the latest workflow status
        4. Optionally updates Terra entities with metadata from workflows
        
        Args:
            days_back: Number of hours to look back for submitted samples
            update_terra: Whether to update Terra entities with metadata
            
        Returns:
            Dictionary with sync results
        """
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized")
        
        # Get samples that have been submitted within the time window
        logger.info(f"Fetching samples submitted in the last {days_back} hours")
        submitted_samples = self.samples_ops.get_samples_by_timeframe(
            timeframe=self.lookup_timeframe,
            days_back=self.lookup_days_back,
            hours_back=self.lookup_hours_back,
            uploaded_filter="uploaded",
            submitted_filter="submitted"
        )
        
        if submitted_samples.empty:
            logger.info(f"No samples found that were submitted in the last {days_back} hours")
            return {"status": "no_data", "synced_count": 0}
        
        # Get samples with Terra submission IDs
        submitted_samples = submitted_samples[submitted_samples["terra_submission_id"].notna()]
        
        if submitted_samples.empty:
            logger.info("No samples found with Terra submission IDs")
            return {"status": "no_data", "synced_count": 0}
        
        # Group samples by terra_submission_id
        submissions_groups = submitted_samples.groupby("terra_submission_id")
        
        total_updated = 0
        failed_updates = []
        
        # Process each submission
        for submission_id, group in submissions_groups:
            if not self.terra:
                # Try to guess the Terra workspace from the first sample's upload_source
                first_sample = group.iloc[0]
                config_id = first_sample.get("config_identifier")
                
                if config_id:
                    config = self.config_ops.get_config(config_id)
                    if config:
                        self.setup_terra_client(config)
                    else:
                        logger.error(f"Could not find configuration for ID: {config_id}")
                        continue
                else:
                    logger.error("No Terra client set up and no config identifier found in sample")
                    continue
            
            try:
                # Get submission status
                submission_status = self.terra.submissions.get_submission_status(submission_id)
                
                # Get workflows for this submission
                workflows = self.terra.submissions.get_workflows_by_submission(submission_id)
                
                # Create a mapping of entity names to workflow statuses
                entity_to_workflow = {}
                for workflow in workflows:
                    if workflow.entity_name:
                        entity_to_workflow[workflow.entity_name] = {
                            "workflow_id": workflow.workflow_id,
                            "status": workflow.status
                        }
                
                # Prepare updates for bigquery
                updates = []
                for _, sample in group.iterrows():
                    sample_id = sample.get("id")
                    entity_id = sample.get("entity_identifier")
                    
                    if entity_id and entity_id in entity_to_workflow:
                        workflow_info = entity_to_workflow[entity_id]
                        updates.append({
                            "id": sample_id,
                            "workflow_state": workflow_info["status"],
                            "terra_workflow_id": workflow_info["workflow_id"],
                            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                
                # Update bigquery with workflow statuses
                if updates:
                    logger.info(f"Updating {len(updates)} records with workflow status for submission {submission_id}")
                    update_result = self.samples_ops.bulk_update_samples(updates)
                    
                    if update_result.get("failed_updates"):
                        failed_updates.extend(update_result["failed_updates"])
                    
                    total_updated += update_result.get("updated_count", 0)
                
                # If requested, update Terra entities with additional metadata
                if update_terra:
                    # Get the sync fields from the sample schema
                    sync_fields = self.samples_ops.get_sync_fields()
                    
                    if sync_fields:
                        for _, sample in group.iterrows():
                            entity_id = sample.get("entity_identifier")
                            
                            if entity_id and entity_id in entity_to_workflow:
                                # Create a dictionary of fields to update
                                entity_updates = {}
                                for field in sync_fields:
                                    if field in sample and sample[field] is not None:
                                        entity_updates[field] = sample[field]
                                
                                if entity_updates:
                                    # Only update if there are fields to update
                                    try:
                                        # Determine entity type from config or default to "data"
                                        config_id = sample.get("config_identifier")
                                        entity_type = "data"  # Default
                                        
                                        if config_id:
                                            config = self.config_ops.get_config(config_id)
                                            if config:
                                                entity_type = config.get("entity_type", "data")
                                        
                                        logger.info(f"Updating Terra entity {entity_id} with fields: {entity_updates.keys()}")
                                        self.terra.entities.update_entity_attributes(
                                            entity_type=entity_type,
                                            entity_id=entity_id,
                                            attributes=entity_updates
                                        )
                                    except Exception as exc:
                                        logger.error(f"Failed to update Terra entity {entity_id}: {str(exc)}")
                
            except Exception as exc:
                logger.error(f"Error processing submission {submission_id}: {str(exc)}")
                failed_updates.append({
                    "submission_id": submission_id,
                    "error": str(exc)
                })
        
        return {
            "status": "success" if total_updated > 0 else "no_updates",
            "synced_count": total_updated,
            "failed_updates": failed_updates
        }
    
    def process_all_configs(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Process all active configurations.
        
        Args:
            entity_type: Optional entity type filter
            
        Returns:
            List of results for each configuration processed
        """
        configs = self.get_active_configs(entity_type=entity_type)
        
        if not configs:
            logger.info(f"No active configurations found" + 
                       (f" for entity type {entity_type}" if entity_type else ""))
            return []
        
        results = []
        for config in configs:
            try:
                logger.info(f"Processing configuration: {config.get('name')} (ID: {config.get('id')})")
                result = self.process_configuration(config)
                results.append(result)
                
                # Log the result
                status = result.get("status")
                if status == "success":
                    logger.info(
                        f"Successfully processed configuration {config.get('id')}: "
                        f"Loaded {result.get('loaded_count')} samples, "
                        f"uploaded {result.get('uploaded_count')} to Terra set {result.get('set_name')}, "
                        f"submitted workflow {result.get('submission_id')} with {result.get('workflow_count')} tasks"
                    )
                elif status == "no_data":
                    logger.info(f"No data found for configuration {config.get('id')}")
                elif status == "no_new_samples":
                    logger.info(
                        f"No new samples to process for configuration {config.get('id')} "
                        f"(loaded: {result.get('loaded')}, filtered: {result.get('filtered')})"
                    )
                else:
                    logger.warning(
                        f"Error processing configuration {config.get('id')}: {result.get('message')}"
                    )
                
            except Exception as exc:
                logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
                results.append({
                    "status": "error",
                    "message": str(exc),
                    "config_id": config.get("id")
                })
        
        return results