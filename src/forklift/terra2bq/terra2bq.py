import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
import pandas as pd
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
        bq_project: str,
        bq_dataset: str,
        bq_location: str = "us-central1",
        bq_credentials: Optional[Dict] = None,
        samples_table: str = "samples",
        configs_table: str = "configs",
        samples_schema_yaml: Optional[Path] = None,
        configs_schema_yaml: Optional[Path] = None,
        source_workspace: Optional[str] = None,
        source_project: Optional[str] = None,
        destination_workspace: Optional[str] = None,
        destination_project: Optional[str] = None,
        metadata_cleanup_fn: Optional[callable] = None,
    ):
        """
        Initialize Terra2BQ with BigQuery and Terra information.
        
        Args:
            bq_project: GCP project ID for BigQuery
            bq_dataset: BigQuery dataset name
            bq_location: BigQuery dataset location
            bq_credentials: Optional service account credentials dict for BigQuery
            samples_table: Name of the samples table in BigQuery
            configs_table: Name of the configs table in BigQuery
            samples_schema_yaml: Path to samples schema YAML file
            configs_schema_yaml: Path to configs schema YAML file
            source_workspace: Default source workspace for Terra, if not provided in configuration
            source_project: Default source project for Terra, if not provided in configuration
            destination_workspace: Destination workspace for Terra, if not provided in configuration
            destination_project:  Destination project for Terra, if not provided in configuration
            metadata_cleanup_fn: Optional function to clean up metadata before upload to BigQuery
        """
        # Initialize bigquery client
        self.bigquery = BigQuery(
            project=bq_project,
            dataset=bq_dataset,
            credentials=bq_credentials,
            location=bq_location,
        )
        
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
        self.destination_workspace = destination_workspace
        self.destination_project = destination_project
        
        # Metadata cleanup function via dependency injection
        self.metadata_cleanup_fn = metadata_cleanup_fn

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
            source_workspace = config.get("terra_workspace")
            if not source_workspace:
                raise ValueError(f"No source workspace provided for configuration {config.get('id')}")
        
        source_project = self.source_project
        if not source_project:
            source_project = config.get("terra_project")
            if not source_project:
                raise ValueError(f"No source project provided for configuration {config.get('id')}")
        
        # Determine destination workspace/project else fall back to source if not specified
        destination_workspace = self.destination_workspace
        if not destination_workspace:
            destination_workspace = config.get("destination_workspace", source_workspace)
        
        destination_project = self.destination_project
        if not destination_project:
            destination_project = config.get("destination_project", source_project)
        
        # Initialize Terra client
        self.terra = Terra(
            source_workspace=source_workspace,
            source_project=source_project,
            destination_workspace=destination_workspace,
            destination_project=destination_project
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
        self.initialize_operations()
        
        if not self.config_ops:
            raise ValueError("Config operations not initialized. Make sure configs_schema_yaml is provided.")
        
        configs = self.config_ops.get_configs(active_only=True, entity_type=entity_type)
        logger.info(f"Found {len(configs)} active configurations" + 
                   (f" for entity type '{entity_type}'" if entity_type else ""))
        
        return configs

    def process_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single configuration by executing the complete workflow.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Dictionary containing results of the operation
        """
        # Get the bigqeury operations objects
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided.")
        
        # Set up Terra client for this configuration
        self.setup_terra_client(config)
        
        # 1. Grab data from Source Terra entity table
        entity_type = config.get("entity_type")
        if not entity_type:
            raise ValueError(f"Configuration {config.get('id')} is missing entity_type field")
        
        logger.info(f"Downloading data from Terra entity type: {entity_type}")
        # Download data from Terra and return dataframe
        terra_df = self.terra.entities.download_table(entity_type)
        
        if terra_df.empty:
            logger.warning(f"No data found in Terra table: {entity_type}")
            return {"status": "no_data", "config_id": config.get("id")}
        
        # 2. Load data into bigquery for unique sample IDs
        logger.info(f"Loading {len(terra_df)} rows into BigQuery")
        load_result = self.samples_ops.load_dataframe(df=terra_df, config=config)
        
        if not load_result.get("success"):
            logger.error(f"Failed to load data into BigQuery: {load_result.get('errors')}")
            return {
                "status": "error", 
                "message": f"Failed to load data: {load_result.get('errors')}",
                "config_id": config.get("id")
            }
        
        # Get the prepared samples that were successfully loaded
        samples_df = self.samples_ops.get_samples_by_timeframe(
            timeframe="today", 
            uploaded_filter="not_uploaded"
        )
        
        if samples_df.empty:
            logger.info("No new samples to process after filtering")
            return {
                "status": "no_new_samples", 
                "loaded": load_result.get("loaded", 0),
                "filtered": load_result.get("filtered", 0),
                "config_id": config.get("id")
            }
        
        # 3. Prepare data for upload to Terra
        # Remove system columns before uploading to Terra
        upload_df = drop_system_value_columns(samples_df, self.samples_schema_yaml)
        
        # 4. Upload data to Terra target
        target_entity = f"{config.get('prefix', 'target')}"
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
        
        # 5. Create a Set name and create Set in Terra
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        set_name = f"{config.get('prefix', 'upload')}_{timestamp}"
        target_entity_set = f"{target_entity}_set"
        
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
        
        # 6. Update bigquery records to indicate they've been uploaded
        # Current datetime in ISO format
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get IDs from the samples DataFrame
        id_values = samples_df["id"].tolist()
        
        # Create updates for bulk update after upload
        updates = [
            {"id": sample_id, "uploaded_at": current_time, "upload_source": set_name}
            for sample_id in id_values
        ]
        
        # Update the records in the sample table
        logger.info(f"Updating {len(updates)} records in BigQuery with upload status")
        update_result = self.samples_ops.bulk_update_samples(updates)
        
        if update_result.get("failed_updates"):
            logger.warning(
                f"Failed to update {len(update_result['failed_updates'])} records in BigQuery"
            )
        
        # 7. Submit a workflow to Terra
        # Get workflow configuration details from config
        terra_method_config = config.get("terra_method_config", {})
        
        # If it's a JSON string, try to parse it or bigquery will throw an error
        if isinstance(terra_method_config, str):
            try:
                terra_method_config = json.loads(terra_method_config)
            except json.JSONDecodeError:
                logger.error(f"Invalid terra_method_config JSON in configuration: {config.get('id')}")
                return {
                    "status": "error", 
                    "message": "Invalid terra_method_config JSON",
                    "config_id": config.get("id")
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
            "entityType": terra_method_config.get("entityType", target_entity_set),
            "entityName": set_name,
            "expression": terra_method_config.get("expression", f"this.{target_entity}s"),
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
            
        except Exception as exc:
            logger.error(f"Failed to submit workflow to Terra: {str(exc)}")
            return {
                "status": "error", 
                "message": f"Failed to submit workflow: {str(exc)}",
                "config_id": config.get("id"),
                "set_name": set_name,
                "uploaded_count": update_result.get("updated_count", 0)
            }
        
        # 8. Update bigquery records with workflow submission information
        # Extract entity names from workflows
        entity_names = []
        for workflow in submission.get("workflows", []):
            entity_name = workflow.get("workflowEntity", {}).get("entityName")
            if entity_name:
                entity_names.append(entity_name)
        
        # Get mapping between entity identifiers and bigquery IDs
        entity_to_id_mapping = self.samples_ops.get_entity_id_mapping()
        
        # Create updates for each entity
        workflow_updates = []
        for entity_name in entity_names:
            # Get the bigquery ID for the entity
            id_value = entity_to_id_mapping.get(entity_name)
            if id_value:
                workflow_updates.append({
                    "id": id_value,
                    "submitted_at": current_time,
                    "terra_submission_id": submission_id,
                    "workflow_state": "Submitted"
                })
        
        # Update bigquery with workflow submission information
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
            "loaded_count": load_result.get("loaded", 0),
            "uploaded_count": update_result.get("updated_count", 0),
            "set_name": set_name,
            "submission_id": submission_id,
            "workflow_count": len(entity_names)
        }
    
    def sync_metadata_from_workflows(
        self, 
        hours_back: int = 24,
        update_terra: bool = True
    ) -> Dict[str, Any]:
        """
        Sync workflow metadata from Terra to BigQuery and optionally back to Terra.
        
        This method:
        1. Gets samples that have been submitted to Terra in the last N hours
        2. Checks Terra for workflow status updates
        3. Updates BigQuery with the latest workflow status
        4. Optionally updates Terra entities with metadata from workflows
        
        Args:
            hours_back: Number of hours to look back for submitted samples
            update_terra: Whether to update Terra entities with metadata
            
        Returns:
            Dictionary with sync results
        """
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized")
        
        # Get samples that have been submitted within the time window
        logger.info(f"Fetching samples submitted in the last {hours_back} hours")
        submitted_samples = self.samples_ops.get_samples_by_timeframe(
            timeframe="custom",
            hours_back=hours_back,
            uploaded_filter="uploaded"  # Only get samples that have been uploaded
        )
        
        if submitted_samples.empty:
            logger.info(f"No samples found that were submitted in the last {hours_back} hours")
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