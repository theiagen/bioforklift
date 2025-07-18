from google.cloud import bigquery
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, timedelta
import logging
from cachetools import TTLCache
import json

logger = logging.getLogger(__name__)


class BigQueryService:
    """BigQuery service for monitoring dashboard queries"""
    
    def __init__(self, project_id: str, dataset_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.client = bigquery.Client(project=project_id)
        
        # Cache for frequent queries (TTL = 5 minutes)
        self.cache = TTLCache(maxsize=100, ttl=300)
        
        # Default table names - can be overridden with environment variables
        self.samples_table = "samples"
        self.configs_table = "configs"
        
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
        return df.to_dict('records')
    
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
        return dict(zip(df['workflow_state'], df['count']))
    
    def get_configuration_metrics(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get metrics by configuration"""
        query = f"""
        SELECT 
            s.config_id,
            c.name as config_name,
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
                    THEN TIMESTAMP_DIFF(s.submitted_at, s.created_at, MINUTE)
                END
            ) as avg_processing_time_minutes
        FROM `{self._get_full_table_name(self.samples_table)}` s
        LEFT JOIN `{self._get_full_table_name(self.configs_table)}` c
            ON s.config_id = c.id
        WHERE s.created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
        GROUP BY s.config_id, c.name
        ORDER BY total_samples DESC
        """
        
        df = self._execute_query(query)
        return df.to_dict('records')
    
    def get_recent_failures(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent failed workflows for debugging"""
        query = f"""
        SELECT 
            s.entity_identifier,
            s.config_id,
            c.name as config_name,
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
        return df.to_dict('records')
    
    def get_processing_time_trends(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Get processing time trends over time"""
        query = f"""
        SELECT 
            DATE(created_at) as date,
            AVG(
                CASE 
                    WHEN submitted_at IS NOT NULL AND created_at IS NOT NULL 
                    THEN TIMESTAMP_DIFF(submitted_at, created_at, MINUTE)
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
        return df.to_dict('records')
    
    def get_active_configurations(self) -> List[Dict[str, Any]]:
        """Get list of active configurations"""
        query = f"""
        SELECT 
            id,
            name,
            state,
            prefix,
            terra_analysis_method,
            active,
            created_at,
            updated_at
        FROM `{self._get_full_table_name(self.configs_table)}`
        WHERE active = TRUE
        ORDER BY name
        """
        
        df = self._execute_query(query)
        return df.to_dict('records')
    
    def get_system_health_metrics(self) -> Dict[str, Any]:
        """Get overall system health metrics"""
        query = f"""
        SELECT 
            COUNT(*) as total_samples,
            COUNT(CASE WHEN created_at >= DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR) 
                       THEN 1 END) as samples_last_24h,
            COUNT(CASE WHEN workflow_state = 'Succeeded' 
                       AND created_at >= DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR) 
                       THEN 1 END) as successful_last_24h,
            COUNT(CASE WHEN workflow_state = 'Failed' 
                       AND created_at >= DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR) 
                       THEN 1 END) as failed_last_24h,
            COUNT(CASE WHEN workflow_state NOT IN ('Succeeded', 'Failed', 'Aborted') 
                       OR workflow_state IS NULL 
                       THEN 1 END) as currently_in_progress
        FROM `{self._get_full_table_name(self.samples_table)}`
        """
        
        df = self._execute_query(query)
        return df.iloc[0].to_dict()
    
    def clear_cache(self):
        """Clear the query cache"""
        self.cache.clear()
        logger.info("Query cache cleared")