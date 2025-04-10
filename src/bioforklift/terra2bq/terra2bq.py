import copy
import json
import sys
from time import sleep
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd
import pytz
from bioforklift.bigquery import BigQuery
from bioforklift.file_transfers import GCSTransferClient
from bioforklift.terra import Terra
from bioforklift.bigquery.utils import drop_system_value_columns
from bioforklift.terra.models import WorkflowConfig
from bioforklift.forklift_logging import setup_logger

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
        
    def _cleanup_terra_client(self):
        """Clean up all resources after processing a configuration."""
        if self.terra:
            self.terra = None
        
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
    
    def _get_terra_data(self, entity_type: str) -> Dict[str, Any]:
        """
        Download data from Terra for a specific entity type.
        
        Args:
            entity_type: Terra entity type
            
        Returns:
            Dictionary with download results and data
        """
        try:
            logger.info(f"Downloading data from Terra entity type: {entity_type}")
            terra_df = self.terra.entities.download_table(entity_type)
            
            if terra_df.empty:
                logger.info(f"No data found in Terra table: {entity_type}")
                return {"status": "no_terra_data", "data": None}
                
            logger.info(f"Downloaded {len(terra_df)} samples from Terra")
            return {"status": "success", "data": terra_df}
            
        except Exception as exc:
            logger.error(f"Failed to download data from Terra: {str(exc)}")
            return {
                "status": "error",
                "message": f"Failed to download data from Terra: {str(exc)}",
                "data": None,
                "error": str(exc)
            }

    def _update_bigquery_with_terra_metadata(
        self,
        config_samples: pd.DataFrame,
        terra_df: pd.DataFrame,
        sync_fields: List[str],
        sample_identifier_field: str,
        update_bigquery: bool = True
    ) -> Dict[str, Any]:
        """
        Update BigQuery records with metadata from Terra.
        
        Args:
            config_samples: DataFrame with BigQuery samples
            terra_df: DataFrame with Terra data
            sync_fields: List of fields to sync
            sample_identifier_field: Field that identifies samples in Terra
            update_bigquery: Whether to actually update BigQuery
            
        Returns:
            {
            "status": "success" if bq_updates else "no_updates",
            "updated_count": updated_count,
            "updated_entities": updated_entities,
            "failed_updates": failed_updates
            }
        """
        bq_updates = []
        updated_entities = {}
        failed_updates = []
        
        # First let's coerce data types to not have issues with mismatches coming from Terra
        self.samples_ops.coerce_dataframe_types(terra_df)
        
        # For each sample in BigQuery, check if it exists in Terra
        # We've seen that the Terra data may have multiple rows for the same entity
        # Or that the entity may not exist in Terra at all because it was filtered out / deleted by user lab
        for _, bq_sample in config_samples.iterrows():
            bq_id = bq_sample['id']
            entity_id = bq_sample[sample_identifier_field]
            
            # Try to find this entity in the Terra data
            terra_rows = terra_df[terra_df.iloc[:, 0] == entity_id]
            
            if terra_rows.empty:
                continue
            
            # Take the first matching row
            terra_row = terra_rows.iloc[0]
            
            # Check each sync field
            sample_update = {'id': bq_id}
            entity_updates = {}
            needs_update = False
            
            for field_to_sync in sync_fields:
                # Skip fields that already have values in BigQuery
                if field_to_sync in bq_sample and pd.notna(bq_sample[field_to_sync]) and bq_sample[field_to_sync] != "":
                    continue
                
                # Get column name in Terra data
                terra_field = self._get_terra_field_name(field_to_sync, terra_row)
                
                if terra_field and pd.notna(terra_row[terra_field]) and terra_row[terra_field] != "":
                    value = terra_row[terra_field]
                    sample_update[field_to_sync] = value
                    entity_updates[field_to_sync] = value
                    needs_update = True
            
            if needs_update:
                bq_updates.append(sample_update)
                updated_entities[entity_id] = entity_updates
        
        # Track updates and failed updates
        updated_count = 0
        
        if bq_updates and update_bigquery:
            logger.info(f"Updating {len(bq_updates)} samples with metadata from Terra")
            try:
                update_result = self.samples_ops.bulk_update_samples(bq_updates)
                
                if update_result.get("failed_updates"):
                    failed_updates.extend(update_result["failed_updates"])
                
                updated_count = update_result.get("updated_count", 0)
                
                # If no actual updates, clear the updated_entities list
                if updated_count == 0:
                    updated_entities = {}
                
            except Exception as update_exc:
                logger.error(f"Error updating samples: {str(update_exc)}")
                failed_updates.append({"error": str(update_exc)})
                updated_entities = {}
        elif bq_updates:
            # Dry run - count but don't perform updates
            logger.info(f"This is a Dry Run, would update {len(bq_updates)} samples with metadata from Terra")
            updated_count = len(bq_updates)
        else:
            logger.info("No updates needed - all sync fields are up to date")
        
        return {
            "status": "success" if bq_updates else "no_updates",
            "updated_count": updated_count,
            "updated_entities": updated_entities,
            "failed_updates": failed_updates
        }

    def _get_terra_field_name(self, field_to_sync: str, terra_row: pd.Series) -> Optional[str]:
        """
        Get the corresponding field name in Terra for a field in BigQuery.
        
        Args:
            field_to_sync: Field name in BigQuery
            terra_row: Row from Terra data
            
        Returns:
            Field name in Terra, or None if not found
        """
        # First try exact match
        if field_to_sync in terra_row:
            return field_to_sync
        
        # Try to find a matching column based on field_attributes.column_mappings
        for col_name in terra_row.index:
            if (field_to_sync in self.samples_ops.field_attributes and 
                'column_mappings' in self.samples_ops.field_attributes[field_to_sync]):
                mappings = self.samples_ops.field_attributes[field_to_sync]['column_mappings']
                if isinstance(mappings, str):
                    mappings = [mappings]
                
                if col_name in mappings:
                    return col_name
        
        return None
    
    def _retroactively_mark_samples_as_uploaded(self, 
                                                config: Dict[str, Any], 
                                                bq_load_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mark newly loaded samples as already uploaded for same-table configuration.
        
        Args:
        config: Configuration dictionary
        bq_load_result: Result from loading data to BigQuery
        
        Returns:
            {
                "status": str,
                "backfilled_count": int
            }
        """
        
        newly_loaded_ids_without_upload = self.samples_ops.get_recent_sample_ids(
            config_id=config.get("id"),
            limit=bq_load_result.get("loaded", 0),
        )
        
        if not newly_loaded_ids_without_upload:
            logger.info("No samples to backfill upload status")
            return {
                "status": "no_samples_to_backfill",
                "backfilled_count": 0
            }
        
        current_datetime = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        current_project_time = datetime.now(pytz.timezone(self.project_timezone)).strftime("%Y%m%d_%H%M%S")
        
        prefix_field = self.config_ops.get_prefix_fields()
        set_name = f"{config.get(prefix_field)}_{current_project_time}"
        
        updates = [
            {'id': sample_id, "uploaded_at": current_datetime, "upload_source": set_name}
            for sample_id in newly_loaded_ids_without_upload
        ]
        
        logger.info(f"Updating {len(updates)} records in BigQuery with backfilled upload status")
        update_result = self.samples_ops.bulk_update_samples(updates)
        
        logger.info(f"Backfilled upload status for {update_result.get('updated_count', 0)} samples")
        
        return {
            "status": "success",
            "backfilled_count": update_result.get("updated_count", 0)
        }
        

    def _update_terra_with_synced_metadata(
        self,
        updated_entities: Dict[str, Dict[str, Any]],
        destination_entity_type: str,
        update_destination: bool = True
    ) -> Dict[str, Any]:
        """
        Update entities in destination Terra datatable.
        
        Args:
            updated_entities: Dictionary mapping entity IDs to attribute updates
            destination_entity_type: Entity type in destination Terra
            update_destination: Whether to actually update Terra
            
        Returns:
            Dictionary with update results
        """
        updated_successfully = 0
        failed_updates = []
        
        if not updated_entities:
            return {
                "status": "no_updates",
                "updated_count": 0,
                "failed_updates": []
            }
        
        logger.info(f"Updating {len(updated_entities)} entities in destination Terra datatable")
        
        for entity_id, attributes in updated_entities.items():
            try:
                logger.debug(f"Updating entity {entity_id} with {attributes} in {destination_entity_type}")
                # Perform the update in terra
                if update_destination:
                    self.terra.entities.update_entity_attributes(
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
                    "entity_id": entity_id,
                    "error": str(terra_exc)
                })
        
        return {
            "status": "success" if updated_successfully > 0 else "no_updates",
            "updated_count": updated_successfully,
            "failed_updates": failed_updates
        }
        
    def _process_submission(
        self,
        config_id: str,
        submission_id: str,
        batch_size: int,
        update_bigquery: bool
    ) -> Dict[str, Any]:
        """
        Process a single submission and update workflow IDs and states.
        
        Args:
            config_id: Configuration ID
            submission_id: Terra submission ID
            batch_size: Number of sample updates to batch together
            update_bigquery: Whether to update BigQuery
            
        Returns:
            Dictionary with processing results
        """
        logger.info(f"Getting workflow information for submission {submission_id}")
        
        try:
            # Get submission status from Terra
            submission_data = self.terra.submissions.get_submission_status(submission_id)
            workflows = submission_data.get('workflows', [])
            
            if not workflows:
                logger.info(f"No workflows found for submission {submission_id}")
                return {
                    "status": "no_workflows",
                    "submission_id": submission_id,
                    "updated_count": 0,
                    "workflow_states": {},
                    "failed_updates": []
                }
            
            # Extract entity names and workflow info
            entity_names = []
            entity_to_workflow = {}
            
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
                return {
                    "status": "no_entities",
                    "submission_id": submission_id,
                    "updated_count": 0,
                    "workflow_states": {},
                    "failed_updates": []
                }
            
            # Get samples matching these entity names
            samples = self.samples_ops.get_samples_by_entity_names(
                config_id=config_id,
                entity_names=entity_names
            )
            
            if samples.empty:
                logger.info(f"No matching samples found for entity names in submission {submission_id}")
                return {
                    "status": "no_samples",
                    "submission_id": submission_id,
                    "updated_count": 0,
                    "workflow_states": {},
                    "failed_updates": []
                }
            
            # Create updates for samples
            sample_id_field = self.samples_ops.get_sample_identifier_field()
            batch_updates = []
            workflow_states = {}
            
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
                    if state not in workflow_states:
                        workflow_states[state] = 0
                    workflow_states[state] += 1
            
            # Apply updates in batches
            update_result = self._apply_batch_updates(
                batch_updates=batch_updates,
                batch_size=batch_size,
                update_bigquery=update_bigquery,
                context=f"submission {submission_id}"
            )
            
            logger.info(f"Processed submission {submission_id}: {update_result.get('updated_count', 0)} samples updated")
            
            return {
                "status": "success" if update_result.get("updated_count", 0) > 0 else "no_updates",
                "submission_id": submission_id,
                "updated_count": update_result.get("updated_count", 0),
                "workflow_states": workflow_states,
                "failed_updates": update_result.get("failed_updates", [])
            }
            
        except Exception as exc:
            logger.error(f"Error processing submission {submission_id}: {str(exc)}")
            return {
                "status": "error",
                "message": str(exc),
                "submission_id": submission_id,
                "updated_count": 0,
                "workflow_states": {},
                "failed_updates": [{
                    "submission_id": submission_id,
                    "error": str(exc)
                }]
            }
            
    def _apply_batch_updates(
        self,
        batch_updates: List[Dict[str, Any]],
        batch_size: int,
        update_bigquery: bool,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        Apply batch updates to BigQuery.
        
        Args:
            batch_updates: List of update dictionaries
            batch_size: Maximum number of updates per batch
            update_bigquery: Whether to actually update BigQuery
            context: Context string for logging
            
        Returns:
            Dictionary with update results
        """
        if not batch_updates:
            return {
                "status": "no_updates",
                "updated_count": 0,
                "failed_updates": []
            }
        
        total_updated = 0
        failed_updates = []
        
        # Apply updates in batches
        if update_bigquery:
            for i in range(0, len(batch_updates), batch_size):
                batch = batch_updates[i:i+batch_size]
                logger.info(f"Updating {len(batch)} samples with workflow information ({context}, batch {i//batch_size + 1})")
                try:
                    update_result = self.samples_ops.bulk_update_samples(batch)
                    
                    if update_result.get("failed_updates"):
                        failed_updates.extend(update_result.get("failed_updates"))
                    
                    total_updated += update_result.get("updated_count", 0)
                except Exception as exc:
                    logger.error(f"Error updating batch {i//batch_size + 1}: {str(exc)}")
                    failed_updates.append({"error": str(exc), "batch": i//batch_size + 1})
        else:
            # Dry run
            logger.info(f"Would update {len(batch_updates)} samples with workflow information (dry run, {context})")
            total_updated = len(batch_updates)
        
        return {
            "status": "success" if total_updated > 0 else "no_updates",
            "updated_count": total_updated,
            "failed_updates": failed_updates
        }

    def _process_incomplete_workflows(
        self,
        config_id: str,
        days_back: int,
        batch_size: int,
        update_bigquery: bool
    ) -> Dict[str, Any]:
        """
        Process samples with incomplete workflow states.
        
        Args:
            config_id: Configuration ID
            days_back: Number of days to look back for samples
            batch_size: Number of sample updates to batch together
            update_bigquery: Whether to update BigQuery
            
        Returns:
            Dictionary with processing results
        """
        try:
            incomplete_samples = self.samples_ops.get_incomplete_workflow_samples(
                config_id=config_id,
                days_back=days_back,
                limit=1000
            )
            
            if incomplete_samples.empty:
                logger.info(f"No samples with incomplete workflow states found for config {config_id}")
                return {
                    "status": "no_incomplete_workflows",
                    "updated_count": 0,
                    "workflow_states": {},
                    "failed_updates": []
                }
            
            logger.info(f"Found {len(incomplete_samples)} samples with incomplete workflow states")
            
            # Process samples and collect state updates
            state_updates = []
            workflow_states = {}
            failed_updates = []
            
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
                            if workflow.status not in workflow_states:
                                workflow_states[workflow.status] = 0
                            workflow_states[workflow.status] += 1
                            break
                    
                    # Apply updates in batches
                    if len(state_updates) >= batch_size:
                        update_result = self._apply_batch_updates(
                            batch_updates=state_updates,
                            batch_size=batch_size,
                            update_bigquery=update_bigquery,
                            context="incomplete workflows"
                        )
                        
                        if update_result.get("failed_updates"):
                            failed_updates.extend(update_result.get("failed_updates"))
                        
                        state_updates = []
                        
                except Exception as workflow_exc:
                    logger.error(f"Error getting workflow metadata for {workflow_id}: {str(workflow_exc)}")
                    failed_updates.append({
                        "workflow_id": workflow_id,
                        "error": str(workflow_exc)
                    })
            
            # Apply any remaining updates
            if state_updates:
                update_result = self._apply_batch_updates(
                    batch_updates=state_updates,
                    batch_size=batch_size,
                    update_bigquery=update_bigquery,
                    context="incomplete workflows (final batch)"
                )
                
                if update_result.get("failed_updates"):
                    failed_updates.extend(update_result.get("failed_updates"))
            
            # Return results
            return {
                "status": "success" if state_updates else "no_updates",
                "updated_count": len(state_updates),
                "workflow_states": workflow_states,
                "failed_updates": failed_updates
            }
                
        except Exception as exc:
            logger.error(f"Error processing incomplete workflows for config {config_id}: {str(exc)}")
            return {
                "status": "error",
                "message": str(exc),
                "updated_count": 0,
                "workflow_states": {},
                "failed_updates": [{
                    "config_id": config_id,
                    "error": f"Failed to process incomplete workflows: {str(exc)}"
                }]
            }
            
    def _process_standard_workflow(self, config: Dict[str, Any], skip_transferred: bool = False) -> Dict[str, Any]:
        """
        Process standard worklfow with separate source and destination datatables.
        This includesuploading to destination and submitting the workflows. 
        
        Args:
        config: Configuration dictionary
        skip_transferred: Whether to mark configs as transferred
        
        Returns:
            Dictionary with upload and submission results
        """
        
        process_result = self.process_upload_and_submit(config)
    
        # If using transient configs, mark them as transferred
        if skip_transferred:
            logger.info(f"Marking configuration {config.get('id')} as transferred")
            self.config_ops.mark_configs_as_transferred(config.get('id'))
        
        return process_result
    
    def _process_single_datatable_workflow(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process workflow submission for single-datatable configurations.
        This skips the upload step and creates entity sets directly from existing data.
        
        Args:
            config: Configuration dictionary
            download_result: Result from download_from_terra_to_bigquery
            
        Returns:
            Dictionary with submission results
        """
        logger.info("Same datatable configuration - skipping upload and proceeding to workflow submission")
        
        # Get samples that were marked as uploaded but not submitted
        samples_df = self.get_samples_for_submission(config)
        
        if samples_df.empty:
            return {
                "status": "no_samples_for_submission",
                "config_id": config.get('id')
            }
        
        try:
            # Get entity type from config
            target_entity = self._get_target_entity_from_config(config)
            
            # Get sample identifiers
            sample_identifier_field = self.samples_ops.get_sample_identifier_field()
            
            # Group samples by their upload_source value
            # This handles the case where multiple batches might be processed together
            upload_sources = samples_df['upload_source'].unique()
            
            submission_results = []
            
            # Process each group of samples with the same upload_source
            for upload_source in upload_sources:
                # Filter samples for this upload_source
                group_samples = samples_df[samples_df['upload_source'] == upload_source]
                group_entity_ids = group_samples[sample_identifier_field].tolist()
                
                # Use the existing upload_source as the set name
                set_name = upload_source
                
                # Create entity set
                logger.info(f"Creating entity set {set_name} with {len(group_entity_ids)} samples")
                self.terra.entities.create_entity_set(
                    set_name=set_name,
                    entity_type=target_entity,
                    entities=group_entity_ids,
                    use_destination=True
                )
                
                # Submit workflow for this group
                group_result = self.submit_workflow(config, set_name, group_samples)
                submission_results.append(group_result)
            
            # Combine results from all submissions
            total_workflow_count = sum(result.get('workflow_count', 0) for result in submission_results if result.get('status') == 'success')
            
            return {
                "status": "success" if any(result.get('status') == 'success' for result in submission_results) else "error",
                "config_id": config.get('id'),
                "set_names": [result.get('set_name') for result in submission_results if result.get('status') == 'success'],
                "submission_ids": [result.get('submission_id') for result in submission_results if result.get('status') == 'success'],
                "workflow_count": total_workflow_count
            }
            
        except Exception as exc:
            logger.error(f"Error creating entity set or submitting workflow: {str(exc)}")
            return {
                "status": "error",
                "message": str(exc),
                "config_id": config.get('id')
            }
        

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

    def get_active_configs(self, entity_type: Optional[str] = None, skip_transferred: bool = False) -> List[Dict[str, Any]]:
        """
        Get active configurations from BigQuery.
        
        Args:
            entity_type: Optional entity type filter
            
        Returns:
            List of active configuration dictionaries
        """
        
        if not self.config_ops:
            raise ValueError("Config operations not initialized. Make sure configs_schema_yaml is provided.")
        
        configs = self.config_ops.get_configs(active_only=True, entity_type=entity_type, skip_transferred=skip_transferred)
        logger.info(f"Found {len(configs)} active configurations" + 
                   (f" for entity type '{entity_type}'" if entity_type else ""))
        
        return configs
    
    def transfer_sequence_files(
        self,
        dataframe: pd.DataFrame, 
        destination_bucket: str,
        preserve_path_structure: bool = False
    ) -> pd.DataFrame:
        """
        Transfer sequence files (fastq, fasta) to a destination bucket and update paths in the dataframe.
        
        Args:
            dataframe: DataFrame containing sample data with GCS file paths
            destination_bucket: Destination GCS bucket name
            
        Returns:
            DataFrame with updated file paths
        """
        # Get sequence file fields from sample operations
        sequence_file_fields = self.samples_ops.get_sequence_file_fields()
        
        if not sequence_file_fields:
            logger.info("No sequence file fields defined in schema, skipping transfer")
            return dataframe
        
        # Create and use transfer client
        transfer_client = GCSTransferClient(
            destination_bucket=destination_bucket,
            credentials=self.google_credentials_json
        )
        
        logger.info(f"Transferring sequence files to destination bucket: {destination_bucket}")
        
        updated_df = transfer_client.transfer_sequence_files(
            dataframe=dataframe,
            sequence_file_columns=sequence_file_fields,
            preserve_path_structure=preserve_path_structure
        )
        
        return updated_df
    
    def download_from_terra_to_bigquery(
        self, 
        config: Dict[str, Any],
        destination_bucket: Optional[str] = None,
        preserve_path_structure: bool = False
    ) -> Dict[str, Any]:
        """
        Pull data from source Terra table and load it into BigQuery.
        
        Args:
            config: Configuration dictionary
            destination_bucket: Optional GCS bucket for transferring sequence files
            preserve_path_structure: Whether to preserve the original path structure (if destination_bucket is provided)
        Returns:
            Dictionary with load results and status
        """
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized. Make sure samples_schema_yaml is provided")
        
        # Set up Terra client for this configuration if not already done
        if not self.terra:
            self.setup_terra_client(config)
            
        # Check for when the source and destination datatables are the same
        is_single_datatable = config.get("single_datatable", False)
        
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
                
        # If a destination bucket is provided, transfer sequence files, and update paths
        if destination_bucket:
            try:
                terra_df = self.transfer_sequence_files(
                    dataframe=terra_df,
                    destination_bucket=destination_bucket,
                    preserve_path_structure=preserve_path_structure
                )
            except Exception as exc:
                # I think this is one case where we don't want a flexible error handling
                # Because if the file transfer fails, we can't proceed with the pipeline
                logger.critical(f"Error transferring sequence files, this will break the pipeline")
                logger.critical(f"Exiting program due to file transer error: {str(exc)}")
                sys.exit(1)
                
        
        # Load data into BigQuery
        logger.info(f"Loading {len(terra_df)} rows into BigQuery")
        bq_load_result = self.samples_ops.load_dataframe(dataframe=terra_df, config=config)
        
        if not bq_load_result.get("success"):
            logger.error(f"Failed to load data into BigQuery: {bq_load_result.get('errors')}")
            return {
                "status": "error", 
                "message": f"Failed to load data: {bq_load_result.get('errors')}",
                "config_id": config.get('id')
            }
            
        # If the source and destination datatables are the same, we need to backfill the upload status
        if is_single_datatable and bq_load_result.get("loaded", 0) > 0:
            logger.info(f"Backfilling upload status for {bq_load_result.get('loaded', 0)} samples")
            backfill_result = self._retroactively_mark_samples_as_uploaded(config, bq_load_result)
            logger.info(f"Backfilled upload status for {backfill_result.get('backfilled_count', 0)} samples")
            
        
        return {
            "status": "success",
            "config_id": config.get('id'),
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
                "config_id": config.get('id')
            }
        
        # Create a Set name and create Set in Terra
        current_datetime = datetime.now(pytz.utc)
        
        # Format for database storage
        current_time_str = current_datetime.strftime("%Y-%m-%d %H:%M:%S")

        # Convert to project timezone
        project_timezone = pytz.timezone(self.project_timezone)
        project_datetime = current_datetime.astimezone(project_timezone)
        # Format for set name in Terra
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
                "config_id": config.get('id')
            }
        
        # Get IDs from the samples DataFrame
        id_values = samples_df['id'].tolist()
        
        # Create updates for bulk update
        updates = [
            {'id': sample_id, "uploaded_at": current_time_str, "upload_source": set_name}
            for sample_id in id_values
        ]
        
        # Update the records in BigQuery
        logger.info(f"Updating {len(updates)} records in BigQuery with upload status")
        update_result = self.samples_ops.bulk_update_samples(updates)
        
        if update_result.get("failed_updates"):
            logger.warning(
                f"Failed to update {len(update_result['failed_updates'])} records in BigQuery"
            )
        
        return {
            "status": "success",
            "config_id": config.get('id'),
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
            config_id = config.get('id')
        
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
        
        # If it's a string JSON like object thing, parse it - this how it comes from BigQuery
        if isinstance(terra_method_config, str):
            try:
                terra_method_config = json.loads(terra_method_config)
            except json.JSONDecodeError:
                logger.error(f"Invalid terra_method_config JSON in configuration: {config.get('id')}")
                return {
                    "status": "error", 
                    "message": "Invalid terra_method_config JSON",
                    "config_id": config.get('id'),
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
        
        # Create WorkflowConfig object to validate and then pass for submission
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
                "config_id": config.get('id'),
                "set_name": set_name
            }
        
        
        current_time = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        # Create updates for each entity
        id_values = samples_df['id'].tolist()
        
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
            "config_id": config.get('id'),
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
                config_id=config.get('id')
            )
            logger.info(f"Samples being uploaded to {str(self.terra.destination_workspace)}: {len(samples_df)}")
            
            if samples_df.empty:
                logger.info(f"No samples to upload today for configuration {config.get('id')}")
                return {
                    "status": "no_new_samples",
                    "config_id": config.get('id')
                }
            
            upload_df = drop_system_value_columns(samples_df, self.samples_schema_yaml)
            logger.info(f"Prepared {len(upload_df)} samples for upload to Terra")
            
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
                    "config_id": config.get('id')
                }
            
            # 3. Get latest sample data after upload
            submission_samples = self.get_samples_for_submission(config, set_name=set_name)
            
            if submission_samples.empty:
                return {
                    "status": "error",
                    "message": "No samples found for submission after upload",
                    "config_id": config.get('id'),
                    "set_name": set_name,
                    "uploaded_count": upload_result.get("uploaded_count", 0)
                }
            
            # 4. Submit workflow
            submission_result = self.submit_workflow(config, set_name, submission_samples)
            logger.debug(f"Submission result: {submission_result}")
            
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
                "config_id": config.get('id')
            }

    def process_configuration(self, config: Dict[str, Any], destination_bucket: Optional[str] = None, 
                              preserve_path_structure: bool = False, skip_transferred: bool = False) -> Dict[str, Any]:
        """
        Process a single configuration to download data from Terra, Upload to BigQuery,
        Upload new samples to destination, and submit a workflow.
        """
        # Create a copy of the configuration to avoid any side effects
        config_copy = copy.deepcopy(config)
        
        # Start with fresh client connections
        self.terra = None
        
        try:
            self.setup_terra_client(config_copy)
            
            # Process in stages with clean state transitions
            download_result = self.download_from_terra_to_bigquery(config_copy, destination_bucket, preserve_path_structure)
            if download_result.get("status") != "success":
                return download_result
            
            is_single_datatable = config_copy.get("single_datatable", False)
            
            if is_single_datatable:
                logger.info(f"Processing same-datatable configuration {config_copy.get('id')}")
                submission_result = self._process_single_datatable_workflow(config_copy)
                    
            else:
                # Standard path to upload to destination and submit
                logger.info(f"Processing standard configuration {config_copy.get('id')}")
                submission_result = self.process_upload_and_submit(config_copy)
                
                # If we are running this process where configs are transient 
                # We want to mark the configs as transferred
                if skip_transferred:
                    logger.info(f"Marking configuration {config_copy.get('id')} as transferred")
                    self.config_ops.mark_configs_as_transferred(config_copy.get('id'))
                    
            # Combine results from both stages
            result = {
                **submission_result,
                "loaded_count": download_result.get("loaded_count", 0),
                "filtered_count": download_result.get("filtered_count", 0)
            }
            
            # Add backfilled count for single-datatable configurations
            if is_single_datatable and "backfilled_count" in download_result:
                result["backfilled_count"] = download_result.get("backfilled_count", 0)
                
            return result
            
        except Exception as exc:
            logger.error(f"Error processing configuration {config_copy.get('id')}: {str(exc)}")
            return {
                "status": "error",
                "message": str(exc),
                "config_id": config_copy.get('id')
            }
            
        finally:
            # Clean up Terra client
            self._cleanup_terra_client()
    
    def process_all_configs(
        self, 
        entity_type: Optional[str] = None,
        batch_size: int = 1,
        cooldown_seconds: int = 1,
        destination_bucket: Optional[str] = None,
        preserve_path_structure: bool = False,
        skip_transferred: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Process all active configurations with progress tracking and batch processing.
        
        Args:
            entity_type: Optional entity type filter
            batch_size: Number of configurations to process in a batch before cooldown
            cooldown_seconds: Seconds to wait between batches (to avoid rate limiting in case we need to scale up)
            destination_bucket: Optional GCS bucket for transferring sequence files
            preserve_path_structure: Whether to preserve the original path structure (if destination_bucket is provided)
            skip_transferred: Whether to skip configurations that have already been transferred (for transient configs)
            
        Returns:
            List of results for each configuration processed
        """
        
        configs = self.get_active_configs(entity_type=entity_type, skip_transferred=skip_transferred)
        
        if not configs:
            logger.info(f"No active configurations found" + 
                    (f" for entity type {entity_type}" if entity_type else ""))
            return []
        
        # Track overall progress
        total_configs = len(configs)
        logger.info(f"Starting processing of {total_configs} configurations" + 
                (f" for entity type {entity_type}" if entity_type else ""))
        
        start_time = datetime.now()
        
        results = []
        for i, config in enumerate(configs):
            # Track the iterative progress
            current_number = i + 1
            percent_complete = (current_number / total_configs) * 100
            
            # Track batch position
            current_batch = (i // batch_size) + 1
            total_batches = (total_configs + batch_size - 1) // batch_size
            in_batch_position = (i % batch_size) + 1
            
            prefix_field = self.config_ops.get_prefix_fields()
            logger.info(
                f"Processing configuration {current_number}/{total_configs} ({percent_complete:.1f}%) - "
                f"Batch {current_batch}/{total_batches}, item {in_batch_position}/{min(batch_size, total_configs - (current_batch-1)*batch_size)}: "
                f"{config.get(str(prefix_field))} (ID: {config.get('id')})"
            )
            
            try:
                # Reset Terra client for each configuration
                self.terra = None
                
                result = self.process_configuration(config, destination_bucket, preserve_path_structure)
                results.append(result)
                
                # We want loggable status messages
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
                        f"(loaded: {result.get('loaded_count', 0)}, filtered: {result.get('filtered_count', 0)})"
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
                    "config_id": config.get('id')
                })
            
            # Add little cooldown between batches, but not after the last one
            if (i + 1) % batch_size == 0 and (i + 1) < total_configs:
                next_batch = current_batch + 1
                logger.info(f"Completed batch {current_batch}/{total_batches}. Cooling down for {cooldown_seconds} seconds before batch {next_batch}...")
                sleep(cooldown_seconds)
    
        end_time = datetime.now()
        duration = end_time - start_time
        minutes, seconds = divmod(duration.total_seconds(), 60)
        
        # Parsing summaries from results for logging & reporting
        success_count = sum(1 for result in results if result.get("status") == "success")
        error_count = sum(1 for result in results if result.get("status") == "error")
        no_data_count = sum(1 for result in results if result.get("status") == "no_data")
        no_samples_count = sum(1 for result in results if result.get("status") == "no_new_samples")
        
        logger.info(
            f"Completed processing {total_configs} configurations in {int(minutes)}m {int(seconds)}s - "
            f"Success: {success_count}, Error: {error_count}, No data: {no_data_count}, No new samples: {no_samples_count}"
        )
        
        return results
    
    def sync_metadata_for_config(
        self,
        config: Dict[str, Any],
        days_back: int,
        update_bigquery: bool = True,
        update_destination: bool = True
    ) -> Dict[str, Any]:
        """
        Sync metadata for a single configuration.
        
        Args:
            config: Configuration dictionary
            days_back: Number of days to look back for samples
            update_bigquery: Whether to update BigQuery with Terra metadata
            update_destination: Whether to update destination Terra datatable
            
        Returns:
            {
                "status": "success" or "no_updates",
                "config_id": config_id,
                "bq_updated_count": bq_result["updated_count"],
                "destination_updated_count": destination_result["updated_count"],
                "failed_updates": bq_result["failed_updates"] + destination_result["failed_updates"]
            }
        """
        config_id = config.get('id')
        entity_type = config.get('entity_type')
        
        if not entity_type:
            logger.warning(f"Configuration {config_id} missing entity_type field, skipping")
            return {
                "status": "error",
                "message": "Missing entity_type field",
                "config_id": config_id,
                "bq_updated_count": 0,
                "destination_updated_count": 0
            }
        
        # Get the field to use as the config identifier for identifying samples
        config_identifier_field = self.samples_ops.get_config_identifier_field()
        if not config_identifier_field:
            logger.warning(f"No config_identifier field defined in sample schema, skipping config {config_id}")
            return {
                "status": "error",
                "message": "No config_identifier field defined",
                "config_id": config_id,
                "bq_updated_count": 0,
                "destination_updated_count": 0
            }
        
        # Get all samples from the timeframe and filter for this configuration
        all_samples_df = self.samples_ops.get_samples_by_timeframe(
            timeframe="custom",
            days_back=days_back,
            uploaded_filter="all",
            submitted_filter="all"
        )
        
        if all_samples_df.empty:
            logger.info(f"No samples found in the last {days_back} days")
            return {
                "status": "no_samples",
                "config_id": config_id,
                "bq_updated_count": 0,
                "destination_updated_count": 0
            }
        
        # Filter samples for this configuration
        config_samples = all_samples_df[all_samples_df[config_identifier_field] == config_id].copy()
        
        if config_samples.empty:
            logger.info(f"No samples found for configuration {config_id}")
            return {
                "status": "no_samples",
                "config_id": config_id,
                "bq_updated_count": 0,
                "destination_updated_count": 0
            }
        
        # Get results from helper functions
        terra_data_result = self._get_terra_data(entity_type)
        if terra_data_result["status"] != "success":
            return {**terra_data_result, "config_id": config_id, "bq_updated_count": 0, "destination_updated_count": 0}
        
        terra_df = terra_data_result["data"]
        sync_fields = self.samples_ops.get_sync_fields()
        sample_identifier_field = self.samples_ops.get_sample_identifier_field()
        
        if not sample_identifier_field:
            return {
                "status": "error",
                "message": "No sample_identifier field defined",
                "config_id": config_id,
                "bq_updated_count": 0,
                "destination_updated_count": 0
            }
        
        # Update BigQuery with Terra metadata
        bq_result = self._update_bigquery_with_terra_metadata(
            config_samples=config_samples,
            terra_df=terra_df,
            sync_fields=sync_fields,
            sample_identifier_field=sample_identifier_field,
            update_bigquery=update_bigquery
        )
        
        # Update destination Terra with updated entities
        destination_result = {"updated_count": 0, "failed_updates": []}
        
        if bq_result["updated_entities"] and update_destination:
            destination_entity_type = self._get_target_entity_from_config(config)
            destination_result = self._update_terra_with_synced_metadata(
                updated_entities=bq_result["updated_entities"],
                destination_entity_type=destination_entity_type,
                update_destination=update_destination
            )
        
        return {
            "status": "success" if (bq_result["updated_count"] > 0 or destination_result["updated_count"] > 0) else "no_updates",
            "config_id": config_id,
            "bq_updated_count": bq_result["updated_count"],
            "destination_updated_count": destination_result["updated_count"],
            "failed_updates": bq_result["failed_updates"] + destination_result["failed_updates"]
        }
    
    def sync_metadata(
        self, 
        days_back: int = 30,
        update_bigquery: bool = True,
        update_destination: bool = True,
        batch_size: int = 1,
        cooldown_seconds: int = 1
    ) -> Dict[str, Any]:
        """
        Sync metadata between Terra data tables and BigQuery, and update destination Terra datatable.
        
        Args:
            days_back: Number of days to look back for samples
            update_bigquery: Whether to update BigQuery with Terra metadata (set to False for dry run)
            update_destination: Whether to update destination Terra datatable (set to False for dry run)
            batch_size: Number of configurations to process in a batch before cooldown
            cooldown_seconds: Seconds to wait between batches
            
        Returns:
            {
            "status": "success",
            "bq_updated_count": 4,
            "destination_updated_count": 4,
            "total_updated_count": 8,
            "processed_configs": 1,
            "failed_updates": 0
            }
        """
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized")
        
        # Get active configurations
        configs = self.get_active_configs()
        
        if not configs:
            logger.info("No active configurations found")
            return {"status": "no_configs", "synced_count": 0}
        
        # Get the fields that should be synced
        sync_fields = self.samples_ops.get_sync_fields()
        if not sync_fields:
            logger.info("No sync fields defined in the sample schema")
            return {"status": "no_sync_fields", "synced_count": 0}
        
        logger.info(f"Found {len(sync_fields)} fields to sync: {sync_fields}")
        
        # Track metrics and progress
        total_configs = len(configs)
        logger.info(f"Starting metadata sync for {total_configs} configurations")
        
        start_time = datetime.now()
        
        bq_updated_count = 0
        destination_updated_count = 0
        failed_updates = []
        processed_configs = 0
        
        for i, config in enumerate(configs):
            # Track progress with batch position
            current_number = i + 1
            percent_complete = (current_number / total_configs) * 100
            current_batch = (i // batch_size) + 1
            total_batches = (total_configs + batch_size - 1) // batch_size
            in_batch_position = (i % batch_size) + 1
            
            prefix_field = self.config_ops.get_prefix_fields()
            logger.info(
                f"Processing configuration {current_number}/{total_configs} ({percent_complete:.1f}%) - "
                f"Batch {current_batch}/{total_batches}, item {in_batch_position}/{min(batch_size, total_configs - (current_batch-1)*batch_size)}: "
                f"{config.get(str(prefix_field))} (ID: {config.get('id')})"
            )
            
            try:
                # Reset Terra client for each configuration
                self.terra = None
                self.setup_terra_client(config)
                
                # Process configuration
                result = self.sync_metadata_for_config(
                    config=config,
                    days_back=days_back,
                    update_bigquery=update_bigquery,
                    update_destination=update_destination
                )
                
                # Update aggregated metrics for reporting
                bq_updated_count += result.get("bq_updated_count", 0)
                destination_updated_count += result.get("destination_updated_count", 0)
                if result.get("failed_updates"):
                    failed_updates.extend(result.get("failed_updates"))
                
                processed_configs += 1
                
                # Informative logging based on result of operation
                status = result.get("status")
                if status == "success":
                    logger.info(
                        f"Successfully processed configuration {config.get('id')}: "
                        f"Updated {result.get('bq_updated_count')} samples in BigQuery, "
                        f"Updated {result.get('destination_updated_count')} entities in Terra"
                    )
                elif status == "no_updates":
                    logger.info(f"No updates needed for configuration {config.get('id')}")
                else:
                    logger.warning(
                        f"Status {status} for configuration {config.get('id')}: {result.get('message', '')}"
                    )
                    
            except Exception as exc:
                logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
                failed_updates.append({
                    "config_id": config.get('id'),
                    "error": str(exc)
                })
            finally:
                # And finally clean up the Terra client before moving to the next configuration
                self._cleanup_terra_client()
            
            # Cooldown between batches, but not after the last one
            if (i + 1) % batch_size == 0 and (i + 1) < total_configs:
                next_batch = current_batch + 1
                logger.info(f"Completed batch {current_batch}/{total_batches}. Cooling down for {cooldown_seconds} seconds before batch {next_batch}...")
                sleep(cooldown_seconds)
        
        # Now that all configurations are processed, log the summary, we will always want to know the time for 
        # The entire operation for scaling considerations
        end_time = datetime.now()
        duration = end_time - start_time
        minutes, seconds = divmod(duration.total_seconds(), 60)
        
        logger.info(
            f"Completed metadata sync in {int(minutes)}m {int(seconds)}s - "
            f"Processed {processed_configs} configurations, "
            f"Updated {bq_updated_count} samples in BigQuery, "
            f"Updated {destination_updated_count} entities in Terra destination"
        )
        
        return {
            "status": "success" if (bq_updated_count > 0 or destination_updated_count > 0) else "no_updates",
            "bq_updated_count": bq_updated_count,
            "destination_updated_count": destination_updated_count,
            "total_updated_count": bq_updated_count + destination_updated_count,
            "processed_configs": processed_configs,
            "failed_updates": failed_updates
        }
    
    def update_workflow_status_for_config(
        self,
        config: Dict[str, Any],
        days_back: int,
        batch_size: int,
        update_bigquery: bool
    ) -> Dict[str, Any]:
        """
        Update workflow status for a single configuration.
        
        Args:
            config: Configuration dictionary
            days_back: Number of days to look back for samples
            batch_size: Number of sample updates to batch together
            update_bigquery: Whether to update BigQuery or Dry Run
            
        Returns:
            {
            "status": "success" or "no_updates",
            "updated_count": total_updated,
            "processed_configs": processed_configs,
            "processed_submissions": submission_count,
            "workflow_states": status_summary,
            "failed_updates": failed_updates
            }
        """
        config_id = config.get('id')
        
        # Get config identifier field
        config_identifier_field = self.samples_ops.get_config_identifier_field()
        if not config_identifier_field:
            logger.warning(f"No config_identifier field defined in sample schema, skipping config {config_id}")
            return {
                "status": "error",
                "message": "No config_identifier field defined",
                "config_id": config_id,
                "updated_count": 0,
                "processed_submissions": 0,
                "workflow_states": {},
                "failed_updates": []
            }
        
        prefix_field = self.config_ops.get_prefix_fields()
        logger.info(f"Processing workflow updates for configuration {config.get(prefix_field)} ({config_id})")
        
        # Get submission IDs
        try:
            submission_ids = self.samples_ops.get_unique_submission_ids(
                config_id=config_id,
                need_workflow_id=True,
                days_back=days_back
            )
            
            logger.info(f"Found {len(submission_ids)} submission IDs to process")
            
            if not submission_ids:
                return {
                    "status": "no_submissions",
                    "config_id": config_id,
                    "updated_count": 0,
                    "processed_submissions": 0,
                    "workflow_states": {},
                    "failed_updates": []
                }
            
        except Exception as exc:
            logger.error(f"Error getting submission IDs: {str(exc)}")
            return {
                "status": "error",
                "message": f"Failed to get submission IDs: {str(exc)}",
                "config_id": config_id,
                "updated_count": 0,
                "processed_submissions": 0,
                "workflow_states": {},
                "failed_updates": [{
                    "config_id": config_id,
                    "error": f"Failed to get submission IDs: {str(exc)}"
                }]
            }
        
        # Process submissions
        total_updated = 0
        failed_updates = []
        workflow_states = {}
        
        for submission_id in submission_ids:
            submission_result = self._process_submission(
                config_id=config_id,
                submission_id=submission_id,
                batch_size=batch_size,
                update_bigquery=update_bigquery
            )
            
            total_updated += submission_result.get("updated_count", 0)
            
            # Update workflow states summary
            for state, count in submission_result.get("workflow_states", {}).items():
                if state not in workflow_states:
                    workflow_states[state] = 0
                workflow_states[state] += count
            
            # Add failed updates to summary
            if submission_result.get("failed_updates"):
                failed_updates.extend(submission_result.get("failed_updates"))
        
        # Process incomplete workflows
        incomplete_result = self._process_incomplete_workflows(
            config_id=config_id,
            days_back=days_back,
            batch_size=batch_size,
            update_bigquery=update_bigquery
        )
        
        total_updated += incomplete_result.get("updated_count", 0)
        
        # Now we can update the workflow states summary
        for state, count in incomplete_result.get("workflow_states", {}).items():
            if state not in workflow_states:
                workflow_states[state] = 0
            workflow_states[state] += count
        
        # Add failed updates
        if incomplete_result.get("failed_updates"):
            failed_updates.extend(incomplete_result.get("failed_updates"))
        
        # Finally return the results summary
        return {
            "status": "success" if total_updated > 0 else "no_updates",
            "config_id": config_id,
            "updated_count": total_updated,
            "processed_submissions": len(submission_ids),
            "workflow_states": workflow_states,
            "failed_updates": failed_updates
        }
        
    def update_workflow_status(
        self, 
        days_back: int = 30,
        batch_size: int = 100,
        update_bigquery: bool = True,
        config_batch_size: int = 4,
        cooldown_seconds: int = 1
    ) -> Dict[str, Any]:
        """
        Update terra_workflow_ids and states from Terra submissions.
        
        This method:
        1. Finds samples in BigQuery that have terra_submission_id but no terra_workflow_id
        2. Fetches workflow information from Terra for each submission
        3. Updates BigQuery records with workflow ids and states
        4. Optionally updates workflow states for workflows with ids but incomplete states
        
        Args:
            days_back: Number of days to look back for samples
            batch_size: Number of sample updates to batch together
            update_bigquery: Whether to update BigQuery
            config_batch_size: Number of configurations to process in a batch before cooldown
            cooldown_seconds: Seconds to wait between configuration batches
            
        Returns:
            {
                "status": "success" or "no_updates",
                "updated_count": total_updated,
                "processed_configs": processed_configs,
                "processed_submissions": submission_count,
                "workflow_states": status_summary,
                "failed_updates": failed_updates
            }
        """
        # Same flow as the other driver functions, trying to make everything follow a similar pattern
        
        self.initialize_operations()
        
        if not self.samples_ops:
            raise ValueError("Sample operations not initialized")
        
        # Get active configurations
        configs = self.get_active_configs()
        if not configs:
            logger.info("No active configurations found")
            return {"status": "no_configs", "updated_count": 0}
        
        # Track metrics and progress
        total_configs = len(configs)
        logger.info(f"Starting workflow status update for {total_configs} configurations")
        
        start_time = datetime.now()
        
        total_updated = 0
        submission_count = 0
        failed_updates = []
        processed_configs = 0
        status_summary = {}
        
        for i, config in enumerate(configs):
            # Track progress with batch position
            current_number = i + 1
            percent_complete = (current_number / total_configs) * 100
            current_batch = (i // config_batch_size) + 1
            total_batches = (total_configs + config_batch_size - 1) // config_batch_size
            in_batch_position = (i % config_batch_size) + 1
            
            prefix_field = self.config_ops.get_prefix_fields()
            logger.info(
                f"Processing configuration {current_number}/{total_configs} ({percent_complete:.1f}%) - "
                f"Batch {current_batch}/{total_batches}, item {in_batch_position}/{min(config_batch_size, total_configs - (current_batch-1)*config_batch_size)}: "
                f"{config.get(str(prefix_field))} (ID: {config.get('id')})"
            )
            
            try:
                # Reset Terra client for each configuration
                self.terra = None
                self.setup_terra_client(config)
                
                # Process configuration
                result = self.update_workflow_status_for_config(
                    config=config,
                    days_back=days_back,
                    batch_size=batch_size,
                    update_bigquery=update_bigquery
                )
                
                # Update aggregated metrics
                total_updated += result.get("updated_count", 0)
                submission_count += result.get("processed_submissions", 0)
                processed_configs += 1
                
                for state, count in result.get("workflow_states", {}).items():
                    if state not in status_summary:
                        status_summary[state] = 0
                    status_summary[state] += count
                
                if result.get("failed_updates"):
                    failed_updates.extend(result.get("failed_updates"))
        
                status = result.get("status")
                if status == "success":
                    logger.info(
                        f"Successfully processed configuration {config.get('id')}: "
                        f"Updated {result.get('updated_count')} workflow records"
                    )
                elif status == "no_updates":
                    logger.info(f"No workflow updates needed for configuration {config.get('id')}")
                elif status == "no_submissions":
                    logger.info(f"No submissions found for configuration {config.get('id')}")
                else:
                    logger.warning(
                        f"Status {status} for configuration {config.get('id')}: {result.get('message', '')}"
                    )
                    
            except Exception as exc:
                logger.error(f"Error processing configuration {config.get('id')}: {str(exc)}")
                failed_updates.append({
                    "config_id": config.get('id'),
                    "error": str(exc)
                })
            finally:
                self._cleanup_terra_client()
            
            if (i + 1) % config_batch_size == 0 and (i + 1) < total_configs:
                next_batch = current_batch + 1
                logger.info(f"Completed batch {current_batch}/{total_batches}. Cooling down for {cooldown_seconds} seconds before batch {next_batch}...")
                sleep(cooldown_seconds)
        
        end_time = datetime.now()
        duration = end_time - start_time
        minutes, seconds = divmod(duration.total_seconds(), 60)
        
        logger.info(
            f"Completed workflow status update in {int(minutes)}m {int(seconds)}s - "
            f"Processed {processed_configs} configurations, "
            f"Updated {total_updated} workflow records"
        )
        
        return {
            "status": "success" if total_updated > 0 else "no_updates",
            "updated_count": total_updated,
            "processed_configs": processed_configs,
            "processed_submissions": submission_count,
            "workflow_states": status_summary,
            "failed_updates": failed_updates
        }