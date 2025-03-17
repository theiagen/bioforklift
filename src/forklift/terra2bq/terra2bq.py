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
from forklift.forklift_logging import setup_logger

logger = setup_logger(__name__)


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
        try:
            method_confiuration = json.loads(config.get("terra_method_config", "{}"))
        except (json.JSONDecodeError, TypeError):
            raise ValueError(f"Invalid terra_method_config JSON in configuration: {config.get('id')}")
            
        target_entity = method_confiuration.get("entityType")
        target_entity_clean = target_entity.replace("_set", "")
        
        return target_entity_clean

    def initialize_operations(self) -> None:
        logger.info("Initializing Terra2BQ operations objects")
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
            destination_workspace = config.get("terra_destination_workspace", destination_workspace)
    
        destination_project = self.destination_project
        if not destination_project:
            destination_project = config.get("terra_destination_project", destination_project)
        
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
                terra_df = self.metadata_cleanup_fn(terra_df, config)
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
        logger.debug(f"Destination datatable: {self.destination_datatable}")
        # Use the target entity from user provided value or configuration
        target_entity = self.destination_datatable
        if not target_entity:
            target_entity = self._get_target_entity_from_config(config)
        logger.debug(f"Uploading {len(upload_df)} samples to Terra entity: {target_entity}")
        
        # Get identifier field for the samples to know which field to transorm to target entity
        sample_identifier_field = self.samples_ops.get_sample_identifier_field()
        logger.debug(f"Sample identifier field: {sample_identifier_field}")
        try:
            uploaded_df = self.terra.entities.upload_entities(
                data=upload_df, 
                target=target_entity,
                entity_identifier_column=str(sample_identifier_field),
                use_destination=True
            )
        except Exception as exc:
            logger.error(f"Failed to upload data to Terra: {str(exc)}")
            return {
                "status": "error", 
                "message": f"Failed to upload to Terra: {str(exc)}",
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
        prefix_field = self.config_ops.get_prefix_fields()
        set_name = f"{config.get(prefix_field)}_{current_project_time}"
        
        logger.info(f"Creating entity set in Terra: {set_name}")
        try:
            self.terra.entities.create_entity_set(
                set_name=set_name,
                entity_type=target_entity,
                entities=uploaded_df,
                use_destination=True
            )
        except Exception as exc:
            logger.error(f"Failed to create entity set in Terra: {str(exc)}")
            return {
                "status": "error", 
                "message": f"Failed to create entity set: {str(exc)}",
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
        
        prefix_field = self.config_ops.get_prefix_fields()
        
        current_datetime = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        # Make backwards compatible
        if 'userCommentTemplate' in terra_method_config:
            terra_method_config['userComment'] = terra_method_config['userCommentTemplate'].format(date=current_datetime)
            del terra_method_config['userCommentTemplate']
        
        # If it's a string (JSON), parse it - this how it comes from BigQuery
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
            "userComment": f"Automated submission for {config.get(str(prefix_field), 'Terra2BQ')}, at {current_datetime}"
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
            
        except Exception as exc:
            logger.error(f"Failed to submit workflow to Terra: {str(exc)}")
            return {
                "status": "error", 
                "message": f"Failed to submit workflow: {str(exc)}",
                "config_id": config.get("id"),
                "set_name": set_name
            }
        
        
        current_time = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        # Create updates for each entity
        id_values = samples_df["id"].tolist()
        
        workflow_updates = [
            {
                "id": id_value,
                "submitted_at": current_time,
                "terra_submission_id": submission_id,
                "workflow_state": "Submitted"
            }
            for id_value in id_values
        ]

        
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
            "workflow_count": len(samples_df)
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
            
            logger.info(f"Processing configuration samples {config.get('id')}")
            samples_df = self.samples_ops.get_samples_by_timeframe(
                timeframe=self.lookup_timeframe,
                days_back=self.lookup_days_back,
                hours_back=self.lookup_hours_back,
                uploaded_filter="not_uploaded",
                config_id=config.get("id")
            )
            logger.info(f"Samples being uploaded to {str(self.terra.destination_workspace)}: {len(samples_df)}")
            
            if samples_df.empty:
                logger.info(f"No samples to upload today for configuration {config.get('id')}")
                return {
                    "status": "no_new_samples",
                    "config_id": config.get("id")
                }
            
            # Prepare upload DataFrame by removing system columns
            upload_df = drop_system_value_columns(samples_df, self.samples_schema_yaml)
            logger.info(f"Prepared {len(upload_df)} samples for upload to Terra")
            
            # 2. Upload data to Terra and create entity set
            upload_result = self.upload_to_terra(config, samples_df, upload_df)
            logger.debug(f"Upload result: {upload_result}")
            if upload_result.get("status") != "success":
                return upload_result
            
            logger.info(f"Upload successful, created entity set: {upload_result.get('set_name')}")
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
            logger.debug(f"Submission result: {submission_result}")
            
            # Combine results
            combined_result = {
                **submission_result,
                "uploaded_count": upload_result.get("uploaded_count", 0)
            }
            
            return combined_result
            
        except Exception as exc:
            logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
            return {
                "status": "error",
                "message": str(exc),
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
            logger.debug(f"Download result: {download_result}")
            
            if download_result.get("status") != "success":
                return download_result
            
            # 2. Upload to Terra and submit workflow
            logger.info(f"Processing configuration {config.get('id')}")
            process_result = self.process_upload_and_submit(config)
            logger.debug(f"Process result: {process_result}")
            
            # Combine results from both steps
            combined_result = {
                **process_result,
                "loaded_count": download_result.get("loaded_count", 0),
                "filtered_count": download_result.get("filtered_count", 0)
            }
            
            return combined_result
            
        except Exception as exc:
            logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
            return {
                "status": "error",
                "message": str(exc),
                "config_id": config.get("id")
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
                prefix_field = self.config_ops.get_prefix_fields()
                logger.info(f"Processing configuration: {config.get(str(prefix_field))} (ID: {config.get('id')})")
                
                # Reset Terra client for each configuration
                self.terra = None
                
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
    
    def sync_metadata_from_workflows(
        self, 
        days_back: int = 30,
        update_bigquery: bool = True,
        update_destination: bool = True
    ) -> Dict[str, Any]:
        """
        Sync metadata between Terra data tables and BigQuery, and update destination Terra datatable.
        
        This method:
        1. Gets samples from BigQuery that were created/updated in the last X days
        2. Downloads Terra data tables for active configurations
        3. Compares fields marked with sync_field=true
        4. Updates BigQuery records where sync fields are empty in BigQuery but filled in Terra
        5. Updates destination Terra datatable ONLY for the entities that were just updated in BigQuery
        
        Args:
            days_back: Number of days to look back for samples
            update_bigquery: Whether to update BigQuery with Terra metadata (set to False for dry run)
            update_destination: Whether to update destination Terra datatable (set to False for dry run)
            
        Returns:
            Dictionary with sync results
        """
        # This is a complex operation that requires multiple steps
        # I needed to put it all here to make it functional and follow the logic
        # But would look good broken down
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized")
        
        # Get active configurations
        configs = self.get_active_configs()
        if not configs:
            logger.info("No active configurations found")
            return {"status": "no_configs", "synced_count": 0}
        
        # Get samples from BigQuery created/updated in specified timeframe
        logger.info(f"Fetching samples created/updated in the last {days_back} days")
        
        # Use custom timeframe with days_back
        bq_samples_df = self.samples_ops.get_samples_by_timeframe(
            timeframe="custom",
            days_back=days_back,
            uploaded_filter="all",  # Get all samples regardless of upload status - here we are syncing metadata
            submitted_filter="all"  # Get all samples regardless of submission status
        )
        
        if bq_samples_df.empty:
            logger.info(f"No samples found in the last {days_back} days")
            return {"status": "no_samples", "synced_count": 0}
        
        # Get the fields that should be synced
        sync_fields = self.samples_ops.get_sync_fields()
        if not sync_fields:
            logger.info("No sync fields defined in the sample schema")
            return {"status": "no_sync_fields", "synced_count": 0}
        
        logger.info(f"Found {len(sync_fields)} fields to sync: {sync_fields}")
        
        # Track metrics for reporting
        bq_updated_count = 0
        destination_updated_count = 0
        failed_updates = []
        processed_configs = 0
        
        # Process each active configuration
        for config in configs:
            try:
                processed_configs += 1
                config_id = config.get('id')
                entity_type = config.get('entity_type')
                
                # Determine destination entity type
                destination_entity_type = self._get_target_entity_from_config(config)
                
                if not entity_type:
                    logger.warning(f"Configuration {config_id} missing entity_type field, skipping")
                    continue
                
                # Set up Terra client for this configuration
                self.setup_terra_client(config)
                
                # Get samples from BigQuery for this configuration
                config_identifier_field = self.samples_ops.get_config_identifier_field()
                if not config_identifier_field:
                    logger.warning(f"No config_identifier field defined in sample schema, skipping config {config_id}")
                    continue
                    
                # Filter samples by this configuration
                config_samples = bq_samples_df[bq_samples_df[config_identifier_field] == config_id].copy()
                
                if config_samples.empty:
                    logger.info(f"No samples found for configuration {config_id}")
                    continue
                
                prefix_field = self.config_ops.get_prefix_fields()
                logger.info(f"Processing {len(config_samples)} samples for configuration {config.get(str(prefix_field))} ({config_id})")
                
                # Get the sample identifier field
                sample_identifier_field = self.samples_ops.get_sample_identifier_field()
                if not sample_identifier_field:
                    logger.warning(f"No sample_identifier field defined in sample schema, skipping config {config_id}")
                    continue
                
                # STEP 1: Download data from Terra and update BigQuery
                terra_df = None
                try:
                    logger.info(f"Downloading data from Terra entity type: {entity_type}")
                    terra_df = self.terra.entities.download_table(entity_type)
                    
                    if terra_df.empty:
                        logger.info(f"No data found in Terra table: {entity_type}")
                        continue
                        
                    logger.info(f"Downloaded {len(terra_df)} samples from Terra")
                    
                except Exception as exc:
                    logger.error(f"Failed to download data from Terra: {str(exc)}")
                    failed_updates.append({
                        "config_id": config_id,
                        "error": f"Failed to download data from Terra: {str(exc)}"
                    })
                    continue
                
                # Prepare updates list for BigQuery
                bq_updates = []
                
                # Dictionary to track which entities were updated and with what fields
                updated_entities = {}
                
                # For each sample in BigQuery, check if it exists in Terra
                for _, bq_sample in config_samples.iterrows():
                    bq_id = bq_sample['id']  # BigQuery primary key
                    entity_id = bq_sample[sample_identifier_field]  # Terra entity identifier
                    
                    # Try to find this entity in the Terra data
                    terra_rows = terra_df[terra_df.iloc[:, 0] == entity_id]
                    
                    if terra_rows.empty:
                        # Entity not found in Terra data
                        continue
                    
                    # Take the first matching row, should only be one for that configuration
                    terra_row = terra_rows.iloc[0]
                    
                    # Check each sync field
                    sample_update = {"id": bq_id}
                    entity_updates = {}
                    needs_update = False
                    
                    for field_to_sync in sync_fields:
                        # Skip fields that already have values in BigQuery
                        if field_to_sync in bq_sample and pd.notna(bq_sample[field_to_sync]) and bq_sample[field_to_sync] != "":
                            continue
                        
                        # Get column name in Terra data, column name might be in terra table or needs to be mapped
                        terra_field = None
                        
                        # First try exact match
                        if field_to_sync in terra_row:
                            terra_field = field_to_sync
                        else:
                            # Try to find a matching column based on field_attributes.column_mappings
                            for col_name in terra_row.index:
                                if (field_to_sync in self.samples_ops.field_attributes and 
                                    'column_mappings' in self.samples_ops.field_attributes[field_to_sync]):
                                    mappings = self.samples_ops.field_attributes[field_to_sync]['column_mappings']
                                    if isinstance(mappings, str):
                                        mappings = [mappings]
                                    
                                    if col_name in mappings:
                                        terra_field = col_name
                                        break
                        
                        if terra_field and pd.notna(terra_row[terra_field]) and terra_row[terra_field] != "":
                            value = terra_row[terra_field]
                            sample_update[field_to_sync] = value
                            entity_updates[field_to_sync] = value
                            needs_update = True
                    
                    if needs_update:
                        bq_updates.append(sample_update)
                        # Track which entities were updated and with what fields
                        updated_entities[entity_id] = entity_updates
                
                # Perform BigQuery updates if any
                if bq_updates and update_bigquery:
                    logger.info(f"Updating {len(bq_updates)} samples with metadata from Terra")
                    try:
                        update_result = self.samples_ops.bulk_update_samples(bq_updates)
                        
                        if update_result.get("failed_updates"):
                            failed_updates.extend(update_result["failed_updates"])
                        
                        actual_updates = update_result.get("updated_count", 0)
                        bq_updated_count += actual_updates
                        
                        logger.info(f"Successfully updated {actual_updates} samples in BigQuery")
                        
                        # If no actual updates, clear the updated_entities list
                        if actual_updates == 0:
                            updated_entities = {}
                        
                    except Exception as update_exc:
                        logger.error(f"Error updating samples for config {config_id}: {str(update_exc)}")
                        failed_updates.append({
                            "config_id": config_id,
                            "error": str(update_exc)
                        })
                        # Clear updated_entities since the update failed
                        updated_entities = {}
                elif bq_updates:
                    # Dry run - don't perform updates
                    logger.info(f"This is a Dry Run, would update {len(bq_updates)} samples with metadata from Terra")
                    bq_updated_count += len(bq_updates)
                else:
                    # No updates needed
                    logger.info(f"No BQ updates needed for config {config_id} - all sync fields are up to date")
                
                # Update only the entities in destination Terra that were just updated in BigQuery
                if updated_entities and update_destination:
                    logger.info(f"Updating {len(updated_entities)} entities in destination Terra datatable that were just updated in BigQuery")
                    updated_successfully = 0
                    
                    for entity_id, attributes in updated_entities.items():
                        try:
                            logger.debug(f"Updating entity {entity_id} with {attributes} in {destination_entity_type}")
                            
                            if update_destination:  # Actually perform the update
                                res = self.terra.entities.update_entity_attributes(
                                    entity_type=destination_entity_type,
                                    entity_id=entity_id,
                                    attributes=attributes,
                                    use_destination=True
                                )
                                updated_successfully += 1
                            else:  # Dry run
                                logger.info(f"Would update entity {entity_id} with {attributes}")
                                updated_successfully += 1
                                
                        except Exception as terra_exc:
                            logger.error(f"Error updating Terra entity {entity_id}: {str(terra_exc)}")
                            failed_updates.append({
                                "config_id": config_id,
                                "entity_id": entity_id,
                                "error": str(terra_exc)
                            })
                    
                    destination_updated_count += updated_successfully
                    logger.info(f"Successfully updated {updated_successfully} entities in destination Terra datatable")
                elif updated_entities:
                    # Dry run with updates
                    logger.info(f"Would update {len(updated_entities)} entities in destination Terra datatable (dry run)")
                    destination_updated_count += len(updated_entities)
                else:
                    # No updates to destination needed
                    logger.info(f"No destination Terra updates needed - no entities were updated in BigQuery")
                    
            except Exception as exc:
                logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
                failed_updates.append({
                    "config_id": config.get('id'),
                    "error": str(exc)
                })
        
        # Return results
        return {
            "status": "success" if (bq_updated_count > 0 or destination_updated_count > 0) else "no_updates",
            "bq_updated_count": bq_updated_count,
            "destination_updated_count": destination_updated_count,
            "total_updated_count": bq_updated_count + destination_updated_count,
            "processed_configs": processed_configs,
            "failed_updates": failed_updates
        }
    
    def update_workflow_status(
        self, 
        days_back: int = 30,
        batch_size: int = 100,
        update_bigquery: bool = True
    ) -> Dict[str, Any]:
        """
        Update workflow_ids and states from Terra submissions.
        
        This method:
        1. Finds samples in BigQuery that have terra_submission_id but no terra_workflow_id
        2. Fetches workflow information from Terra for each submission
        3. Updates BigQuery records with workflow ids and states
        4. Optionally updates workflow states for workflows with ids but incomplete states
        
        Args:
            days_back: Number of days to look back for samples
            batch_size: Number of updates to batch together
            update_bigquery: Whether to update BigQuery
            
        Returns:
            Dictionary with update results
        """
        # Same thing as function above, will want to make this more modular
        # But need to follow the logic all the way down first
        # I struggle with breaking things down for bigquery since it's so operationally heavy
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized")
        
        # Get active configurations
        configs = self.get_active_configs()
        if not configs:
            logger.info("No active configurations found")
            return {"status": "no_configs", "updated_count": 0}
        
        # Track metrics for reporting
        total_updated = 0
        submission_count = 0
        failed_updates = []
        processed_configs = 0
        status_summary = {}
        
        # Process each active configuration
        for config in configs:
            try:
                processed_configs += 1
                config_id = config.get('id')
                
                # Set up Terra client for this configuration
                self.setup_terra_client(config)
                
                # Get config identifier field
                config_identifier_field = self.samples_ops.get_config_identifier_field()
                if not config_identifier_field:
                    logger.warning(f"No config_identifier field defined in sample schema, skipping config {config_id}")
                    continue
                
                logger.info(f"Processing workflow updates for configuration {config.get('name')} ({config_id})")
                
                # First we need to grab submission ids for config
                try:
                    submission_ids = self.samples_ops.get_unique_submission_ids(
                        config_id=config_id,
                        need_workflow_id=True,
                        days_back=days_back
                    )
                    
                    submission_count += len(submission_ids)
                    logger.info(f"Found {len(submission_ids)} submission IDs to process")
                    
                except Exception as exc:
                    logger.error(f"Error getting submission IDs: {str(exc)}")
                    failed_updates.append({
                        "config_id": config_id,
                        "error": f"Failed to get submission IDs: {str(exc)}"
                    })
                    continue
                
                # Then we need to process each submission
                for submission_id in submission_ids:
                    try:
                        # Get submission status from Terra
                        logger.info(f"Getting workflow information for submission {submission_id}")
                        # Already using destination datatable, default set to true
                        submission_data = self.terra.submissions.get_submission_status(submission_id)
                        workflows = submission_data.get('workflows', [])
                        
                        if not workflows:
                            logger.info(f"No workflows found for submission {submission_id}")
                            continue
                        
                        # Extract entity names from workflows
                        entity_names = []
                        entity_to_workflow = {}
                        
                        # Maybe move parsing terra parsing functions to terra client/utils
                        for workflow in workflows:
                            if 'workflowEntity' in workflow and 'entityName' in workflow['workflowEntity']:
                                entity_name = workflow['workflowEntity']['entityName']
                                entity_names.append(entity_name)
                                entity_to_workflow[entity_name] = {
                                    'workflow_id': workflow.get('workflowId', ''),
                                    'state': workflow.get('status', 'Unknown')
                                }
                        
                        if not entity_names:
                            logger.info(f"No entity names found in workflows for submission {submission_id}")
                            continue
                        
                        # Get samples matching these entity names
                        samples = self.samples_ops.get_samples_by_entity_names(
                            config_id=config_id,
                            entity_names=entity_names
                        )
                        
                        if samples.empty:
                            logger.info(f"No matching samples found for entity names in submission {submission_id}")
                            continue
                        
                        # Create updates for samples
                        sample_id_field = self.samples_ops.get_sample_identifier_field()
                        batch_updates = []
                        
                        for _, sample in samples.iterrows():
                            entity_id = sample.get(sample_id_field)
                            if entity_id in entity_to_workflow:
                                workflow_info = entity_to_workflow[entity_id]
                                batch_updates.append({
                                    'id': sample.get('id'),
                                    'terra_workflow_id': workflow_info['workflow_id'],
                                    'workflow_state': workflow_info['state']
                                })
                                
                                # Update status summary
                                state = workflow_info['state']
                                if state not in status_summary:
                                    status_summary[state] = 0
                                status_summary[state] += 1
                        
                        # Apply updates in batches, I was doing this to avoid overloading Terra API in previous iterations
                        # But it might not be necessary, was necessary before when I was backfilling data
                        if batch_updates and update_bigquery:
                            for i in range(0, len(batch_updates), batch_size):
                                batch = batch_updates[i:i+batch_size]
                                logger.info(f"Updating {len(batch)} samples with workflow information (batch {i//batch_size + 1})")
                                update_result = self.samples_ops.bulk_update_samples(batch)
                                
                                if update_result.get("failed_updates"):
                                    failed_updates.extend(update_result["failed_updates"])
                                
                                total_updated += update_result.get("updated_count", 0)
                        elif batch_updates:
                            # Dry run
                            logger.info(f"Would update {len(batch_updates)} samples with workflow information (dry run)")
                            total_updated += len(batch_updates)
                        
                        logger.info(f"Processed submission {submission_id}: {len(batch_updates)} samples updated")
                        
                    except Exception as submission_exc:
                        logger.error(f"Error processing submission {submission_id}: {str(submission_exc)}")
                        failed_updates.append({
                            "config_id": config_id,
                            "submission_id": submission_id,
                            "error": str(submission_exc)
                        })
                
                # Check for incomplete workflows in case metadata was not updated immediately after submission
                # Me and Andrew Hale noticed this happening
                try:
                    incomplete_samples = self.samples_ops.get_incomplete_workflow_samples(
                        config_id=config_id,
                        days_back=days_back,
                        limit=1000
                    )
                    
                    if not incomplete_samples.empty:
                        logger.info(f"Found {len(incomplete_samples)} samples with incomplete workflow states")
                        
                        # Process in batches to avoid overloading Terra API
                        state_updates = []
                        
                        for _, sample in incomplete_samples.iterrows():
                            sample_id = sample.get('id')
                            workflow_id = sample.get('terra_workflow_id')
                            submission_id = sample.get('terra_submission_id')
                            
                            try:
                                # Get workflow metadata
                                workflows = self.terra.submissions.get_workflows_by_submission(submission_id)
                                
                                # Find matching workflow
                                for workflow in workflows:
                                    if workflow.workflow_id == workflow_id:
                                        state_updates.append({
                                            'id': sample_id,
                                            'workflow_state': workflow.status
                                        })
                                        
                                        # Update status summary
                                        if workflow.status not in status_summary:
                                            status_summary[workflow.status] = 0
                                        status_summary[workflow.status] += 1
                                        break
                                
                                # Apply updates in batches
                                if len(state_updates) >= batch_size:
                                    if update_bigquery:
                                        logger.info(f"Updating {len(state_updates)} workflow states")
                                        update_result = self.samples_ops.bulk_update_samples(state_updates)
                                        
                                        if update_result.get("failed_updates"):
                                            failed_updates.extend(update_result["failed_updates"])
                                        
                                        total_updated += update_result.get("updated_count", 0)
                                    else:
                                        # Dry run
                                        logger.info(f"Would update {len(state_updates)} workflow states (dry run)")
                                        total_updated += len(state_updates)
                                    
                                    state_updates = []
                                    
                            except Exception as workflow_exc:
                                logger.error(f"Error getting workflow metadata for {workflow_id}: {str(workflow_exc)}")
                        
                        # Update any remaining state updates
                        if state_updates and update_bigquery:
                            logger.info(f"Updating {len(state_updates)} workflow states")
                            update_result = self.samples_ops.bulk_update_samples(state_updates)
                            
                            if update_result.get("failed_updates"):
                                failed_updates.extend(update_result["failed_updates"])
                            
                            total_updated += update_result.get("updated_count", 0)
                        elif state_updates:
                            # Dry run
                            logger.info(f"Would update {len(state_updates)} workflow states (dry run)")
                            total_updated += len(state_updates)
                            
                except Exception as incomplete_exc:
                    logger.error(f"Error processing incomplete workflows: {str(incomplete_exc)}")
                    failed_updates.append({
                        "config_id": config_id,
                        "error": f"Failed to process incomplete workflows: {str(incomplete_exc)}"
                    })
                
            except Exception as exc:
                logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
                failed_updates.append({
                    "config_id": config.get('id'),
                    "error": str(exc)
                })
        
        # Return summary of workflow status results
        return {
            "status": "success" if total_updated > 0 else "no_updates",
            "updated_count": total_updated,
            "processed_configs": processed_configs,
            "processed_submissions": submission_count,
            "workflow_states": status_summary,
            "failed_updates": failed_updates
        }