from google.cloud import bigquery
from typing import List, Dict, Any
import pandas as pd
import numpy as np
import logging
import os
from cachetools import TTLCache

logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """Recursively convert numpy/pandas types to native Python types"""
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, 'item'):  # Generic numpy scalar
        return obj.item()
    elif pd.isna(obj):  # pandas NaN
        return None
    else:
        return obj


class BigQueryService:
    """BigQuery service for monitoring dashboard queries"""
    
    def __init__(self, project_id: str, dataset_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.client = bigquery.Client(project=project_id)
        
        # Cache for frequent queries (TTL = 5 minutes)
        self.cache = TTLCache(maxsize=100, ttl=300)
        
        # Get table names from environment variables
        self.samples_table = os.getenv('BIGQUERY_SAMPLES_TABLE', 'samples')
        self.configs_table = os.getenv('BIGQUERY_CONFIGS_TABLE', 'configs')
        
        # Column mappings for different table schemas
        # Maps BigQuery column names to standardized field names used in Pydantic models
        self.column_mappings = {
            'samples': {
                # Standard mapping - can be overridden
                'entity_identifier': 'entity_identifier',
                'config_id': 'config_id', 
                'workflow_state': 'workflow_state',
                'created_at': 'created_at',
                'submitted_at': 'submitted_at',
                'terra_submission_id': 'terra_submission_id',
                'terra_workflow_id': 'terra_workflow_id'
            },
            'configs': {
                'id': 'id',
                'name': 'name', 
                'state': 'state',
                'prefix': 'prefix',
                'terra_analysis_method': 'terra_analysis_method',
                'active': 'active',
                'created_at': 'created_at',
                'updated_at': 'updated_at'
            }
        }
        
        # Load custom column mappings from environment if provided
        self._load_column_mappings_from_env()
        
    def _load_column_mappings_from_env(self):
        """Load custom column mappings from environment variables"""
        import json
        
        # Example: BIGQUERY_SAMPLES_COLUMNS='{"sample_id":"entity_identifier","config":"config_id"}'
        samples_mapping = os.getenv('BIGQUERY_SAMPLES_COLUMNS')
        if samples_mapping:
            try:
                custom_mapping = json.loads(samples_mapping)
                self.column_mappings['samples'].update(custom_mapping)
                logger.info(f"Loaded custom samples column mapping: {custom_mapping}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in BIGQUERY_SAMPLES_COLUMNS: {e}")
        
        configs_mapping = os.getenv('BIGQUERY_CONFIGS_COLUMNS')
        if configs_mapping:
            try:
                custom_mapping = json.loads(configs_mapping)
                self.column_mappings['configs'].update(custom_mapping)
                logger.info(f"Loaded custom configs column mapping: {custom_mapping}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in BIGQUERY_CONFIGS_COLUMNS: {e}")
    
    def _apply_column_mapping(self, records: List[Dict[str, Any]], table_type: str) -> List[Dict[str, Any]]:
        """Apply column mapping to transform BigQuery columns to standardized field names"""
        if table_type not in self.column_mappings:
            return records
        
        mapping = self.column_mappings[table_type]
        mapped_records = []
        
        for record in records:
            mapped_record = {}
            for bq_col, standard_field in mapping.items():
                if bq_col in record:
                    mapped_record[standard_field] = record[bq_col]
            
            # Include any unmapped columns as-is
            for col, value in record.items():
                if col not in mapping and col not in mapped_record:
                    mapped_record[col] = value
            
            mapped_records.append(mapped_record)
        
        return mapped_records
    
    def _get_full_table_name(self, table_name: str) -> str:
        """Get full table name with project and dataset"""
        return f"{self.project_id}.{self.dataset_id}.{table_name}"
    
    def _execute_query(self, query: str, use_cache: bool = True) -> pd.DataFrame:
        """Execute a BigQuery query and return results as DataFrame"""
        cache_key = hash(query) if use_cache else None
        
        if use_cache and cache_key in self.cache:
            logger.info("Returning cached query result")
            return self.cache[cache_key]
        
        try:
            logger.info(f"Executing BigQuery query: {query[:100]}...")
            result = self.client.query(query).to_dataframe()
            
            # Force all numeric columns to use native Python types
            for col in result.columns:
                if result[col].dtype.kind in 'biufc':  # numeric types
                    if result[col].dtype.kind in 'biu':  # integer types
                        result[col] = result[col].astype('Int64')  # Nullable integer
                    else:  # float types
                        result[col] = result[col].astype('float64')
            
            if use_cache:
                self.cache[cache_key] = result
                
            return result
            
        except Exception as e:
            logger.error(f"BigQuery query failed: {e}")
            raise
    
    def get_daily_runs_summary(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get daily runs summary for the last N days"""
        query = f"""
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as total_runs,
            COUNT(CASE WHEN workflow_state = 'Succeeded' THEN 1 END) as successful_runs,
            COUNT(CASE WHEN workflow_state = 'Failed' THEN 1 END) as failed_runs,
            COUNT(CASE WHEN workflow_state = 'Aborted' THEN 1 END) as aborted_runs,
            COUNT(CASE WHEN workflow_state NOT IN ('Succeeded', 'Failed', 'Aborted') 
                       OR workflow_state IS NULL THEN 1 END) as in_progress_runs
        FROM `{self._get_full_table_name(self.samples_table)}`
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """
        
        df = self._execute_query(query)
        # Convert count columns to integers, handling NaN values
        count_columns = ['total_runs', 'successful_runs', 'failed_runs', 'aborted_runs', 'in_progress_runs']
        for col in count_columns:
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(int)
        
        # Convert to records and ensure proper Python types
        records = df.to_dict('records')
        for record in records:
            for col in count_columns:
                if col in record and record[col] is not None:
                    # Convert pandas nullable int to Python int
                    val = record[col]
                    record[col] = int(val) if hasattr(val, 'item') else int(val)
        return records
    
    def get_workflow_states_distribution(self, days_back: int = 7) -> Dict[str, int]:
        """Get workflow states distribution for recent period"""
        query = f"""
        SELECT 
            COALESCE(workflow_state, 'Unknown') as workflow_state,
            COUNT(*) as count
        FROM `{self._get_full_table_name(self.samples_table)}`
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
        GROUP BY workflow_state
        ORDER BY count DESC
        """
        
        df = self._execute_query(query)
        # Convert count column to int, handling NaN values
        df['count'] = df['count'].fillna(0).astype(int)
        return dict(zip(df['workflow_state'], df['count']))
    
    def get_configuration_metrics(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get metrics by configuration"""
        # Get actual column names from mapping (reverse lookup)
        mapping = self.column_mappings.get('configs', {})
        reverse_mapping = {v: k for k, v in mapping.items()}
        
        # Use actual BigQuery column names
        name_col = reverse_mapping.get('name', 'name')
        
        query = f"""
        SELECT 
            s.config_id,
            c.{name_col} as config_name,
            COUNT(*) as total_samples,
            COUNT(CASE WHEN s.workflow_state = 'Succeeded' THEN 1 END) as successful_samples,
            COUNT(CASE WHEN s.workflow_state = 'Failed' THEN 1 END) as failed_samples,
            ROUND(
                COUNT(CASE WHEN s.workflow_state = 'Succeeded' THEN 1 END) * 100.0 / COUNT(*), 
                2
            ) as success_rate,
            AVG(
                CASE 
                    WHEN s.submitted_at IS NOT NULL AND s.created_at IS NOT NULL 
                    THEN DATETIME_DIFF(s.submitted_at, s.created_at, MINUTE)
                END
            ) as avg_processing_time_minutes
        FROM `{self._get_full_table_name(self.samples_table)}` s
        LEFT JOIN `{self._get_full_table_name(self.configs_table)}` c
            ON s.config_id = c.id
        WHERE s.created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
        GROUP BY s.config_id, c.{name_col}
        ORDER BY total_samples DESC
        """
        
        df = self._execute_query(query)
        # Convert count columns to integers, handling NaN values
        count_columns = ['total_samples', 'successful_samples', 'failed_samples']
        for col in count_columns:
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(int)
        # Convert float columns to native Python floats, handling NaN values
        if 'success_rate' in df.columns:
            df['success_rate'] = df['success_rate'].fillna(0.0).astype(float)
        if 'avg_processing_time_minutes' in df.columns:
            # Keep None for optional fields
            df['avg_processing_time_minutes'] = df['avg_processing_time_minutes'].where(df['avg_processing_time_minutes'].notna(), None)
        
        # Convert to records and ensure proper Python types
        records = df.to_dict('records')
        for record in records:
            for col in count_columns:
                if col in record and record[col] is not None:
                    val = record[col]
                    record[col] = int(val) if hasattr(val, 'item') else int(val)
            if 'success_rate' in record and record['success_rate'] is not None:
                val = record['success_rate']
                record['success_rate'] = float(val) if hasattr(val, 'item') else float(val)
            if 'avg_processing_time_minutes' in record and record['avg_processing_time_minutes'] is not None:
                val = record['avg_processing_time_minutes']
                record['avg_processing_time_minutes'] = float(val) if hasattr(val, 'item') else float(val)
        return records
    
    def get_recent_failures(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent failed workflows for debugging"""
        # Get actual column names from mapping (reverse lookup)
        mapping = self.column_mappings.get('configs', {})
        reverse_mapping = {v: k for k, v in mapping.items()}
        
        # Use actual BigQuery column names
        name_col = reverse_mapping.get('name', 'name')
        
        query = f"""
        SELECT 
            s.entity_identifier,
            s.config_id,
            c.{name_col} as config_name,
            s.workflow_state,
            s.created_at,
            s.submitted_at,
            s.terra_submission_id,
            s.terra_workflow_id
        FROM `{self._get_full_table_name(self.samples_table)}` s
        LEFT JOIN `{self._get_full_table_name(self.configs_table)}` c
            ON s.config_id = c.id
        WHERE s.workflow_state = 'Failed'
        ORDER BY s.created_at DESC
        LIMIT {limit}
        """
        
        df = self._execute_query(query)
        records = df.to_dict('records')
        records = convert_numpy_types(records)
        return self._apply_column_mapping(records, 'samples')
    
    def get_processing_time_trends(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get processing time trends over time"""
        query = f"""
        SELECT 
            DATE(created_at) as date,
            AVG(
                CASE 
                    WHEN submitted_at IS NOT NULL AND created_at IS NOT NULL 
                    THEN DATETIME_DIFF(submitted_at, created_at, MINUTE)
                END
            ) as avg_processing_time_minutes,
            COUNT(*) as sample_count
        FROM `{self._get_full_table_name(self.samples_table)}`
        WHERE created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
            AND submitted_at IS NOT NULL
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """
        
        df = self._execute_query(query)
        # Convert count column to int, handling NaN values
        if 'sample_count' in df.columns:
            df['sample_count'] = df['sample_count'].fillna(0).astype(int)
        # Convert float columns to native Python floats, handling NaN values
        if 'avg_processing_time_minutes' in df.columns:
            # Keep None for optional fields
            df['avg_processing_time_minutes'] = df['avg_processing_time_minutes'].where(df['avg_processing_time_minutes'].notna(), None)
        
        # Convert to records and ensure proper Python types
        records = df.to_dict('records')
        for record in records:
            if 'sample_count' in record and record['sample_count'] is not None:
                val = record['sample_count']
                record['sample_count'] = int(val) if hasattr(val, 'item') else int(val)
            if 'avg_processing_time_minutes' in record and record['avg_processing_time_minutes'] is not None:
                val = record['avg_processing_time_minutes']
                record['avg_processing_time_minutes'] = float(val) if hasattr(val, 'item') else float(val)
        return records
    
    def get_active_configurations(self) -> List[Dict[str, Any]]:
        """Get list of active configurations"""
        # Get actual column names from mapping (reverse lookup)
        mapping = self.column_mappings.get('configs', {})
        reverse_mapping = {v: k for k, v in mapping.items()}
        
        # Debug logging
        logger.info(f"Debug - configs mapping: {mapping}")
        logger.info(f"Debug - reverse mapping: {reverse_mapping}")
        
        # Use actual BigQuery column names in query
        id_col = reverse_mapping.get('id', 'id')
        name_col = reverse_mapping.get('name', 'name')
        state_col = reverse_mapping.get('state', 'state')
        prefix_col = reverse_mapping.get('prefix', 'prefix')
        terra_method_col = reverse_mapping.get('terra_analysis_method', 'terra_analysis_method')
        active_col = reverse_mapping.get('active', 'active')
        created_col = reverse_mapping.get('created_at', 'created_at')
        updated_col = reverse_mapping.get('updated_at', 'updated_at')
        
        logger.info(f"Debug - name_col resolved to: {name_col}")
        
        query = f"""
        SELECT 
            {id_col} as id,
            {name_col} as name,
            {state_col} as state,
            {prefix_col} as prefix,
            {terra_method_col} as terra_analysis_method,
            {active_col} as active,
            {created_col} as created_at,
            {updated_col} as updated_at
        FROM `{self._get_full_table_name(self.configs_table)}`
        WHERE {active_col} = TRUE
        ORDER BY {name_col}
        """
        
        df = self._execute_query(query)
        records = df.to_dict('records')
        return convert_numpy_types(records)
    
    def get_system_health_metrics(self) -> Dict[str, Any]:
        """Get overall system health metrics"""
        query = f"""
        SELECT 
            COUNT(*) as total_samples,
            COUNT(CASE WHEN created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                       THEN 1 END) as samples_last_24h,
            COUNT(CASE WHEN workflow_state = 'Succeeded' 
                       AND created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                       THEN 1 END) as successful_last_24h,
            COUNT(CASE WHEN workflow_state = 'Failed' 
                       AND created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                       THEN 1 END) as failed_last_24h,
            COUNT(CASE WHEN workflow_state NOT IN ('Succeeded', 'Failed', 'Aborted') 
                       OR workflow_state IS NULL 
                       THEN 1 END) as currently_in_progress,
            CASE 
                WHEN COUNT(CASE WHEN created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) THEN 1 END) = 0 THEN 0.0
                ELSE ROUND((COUNT(CASE WHEN workflow_state = 'Succeeded' 
                                       AND created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                                       THEN 1 END) / 
                           COUNT(CASE WHEN created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                                      THEN 1 END)) * 100, 2)
            END as success_rate_24h,
            CASE 
                WHEN COUNT(CASE WHEN created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) THEN 1 END) = 0 THEN 0.0
                ELSE ROUND((COUNT(CASE WHEN workflow_state = 'Failed' 
                                       AND created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                                       THEN 1 END) / 
                           COUNT(CASE WHEN created_at >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
                                      THEN 1 END)) * 100, 2)
            END as failure_rate_24h
        FROM `{self._get_full_table_name(self.samples_table)}`
        """
        
        df = self._execute_query(query)
        # Convert count columns to integers, handling NaN values
        count_columns = ['total_samples', 'samples_last_24h', 'successful_last_24h', 'failed_last_24h', 'currently_in_progress']
        for col in count_columns:
            if col in df.columns:
                df[col] = df[col].fillna(0).astype(int)
        # Convert float columns to native Python floats, handling NaN values
        float_columns = ['success_rate_24h', 'failure_rate_24h']
        for col in float_columns:
            if col in df.columns:
                df[col] = df[col].fillna(0.0).astype(float)
        
        # Convert to dict and ensure proper Python types
        record = df.iloc[0].to_dict()
        return convert_numpy_types(record)
    
    def clear_cache(self):
        """Clear the query cache"""
        self.cache.clear()
        logger.info("Query cache cleared")