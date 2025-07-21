import axios from 'axios';
import { handleAuthError } from '$lib/auth';

// API types
export interface DailyRunSummary {
  date: string; // Date is serialized as string over JSON
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  aborted_runs: number;
  in_progress_runs: number;
  success_rate: number; // Computed property from backend
}

export interface WorkflowStateDistribution {
  workflow_states: Record<string, number>;
  total_workflows: number; // Computed property from backend
}

export interface ConfigurationMetrics {
  config_id: string;
  config_name: string | null;
  total_samples: number;
  successful_samples: number;
  failed_samples: number;
  success_rate: number;
  avg_processing_time_minutes: number | null;
}

export interface RecentFailure {
  entity_identifier: string;
  config_id: string | null;
  config_name: string | null;
  workflow_state: string;
  created_at: string; // DateTime is serialized as string over JSON
  submitted_at: string | null; // DateTime is serialized as string over JSON
  terra_submission_id: string | null;
  terra_workflow_id: string | null;
}

export interface ProcessingTimeTrend {
  date: string; // Date is serialized as string over JSON
  avg_processing_time_minutes: number | null;
  sample_count: number;
}

export interface ActiveConfiguration {
  id: string;
  name: string;
  state: string;
  prefix: string;
  terra_analysis_method: string;
  active: boolean;
  created_at: string; // DateTime is serialized as string over JSON
  updated_at: string | null; // DateTime is serialized as string over JSON
}

export interface SystemHealthMetrics {
  total_samples: number;
  samples_last_24h: number;
  successful_last_24h: number;
  failed_last_24h: number;
  currently_in_progress: number;
  success_rate_24h: number;
  failure_rate_24h: number;
}

export interface DashboardMetrics {
  daily_runs: DailyRunSummary[];
  workflow_distribution: WorkflowStateDistribution;
  configuration_metrics: ConfigurationMetrics[];
  recent_failures: RecentFailure[];
  processing_trends: ProcessingTimeTrend[];
  active_configurations: ActiveConfiguration[];
  system_health: SystemHealthMetrics;
}

// API client configuration
const API_BASE_URL = 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Include cookies for session management
});

// Add request interceptor for logging
apiClient.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Response Error:', error);
    
    // Handle authentication errors
    if (error.response?.status === 401 || error.response?.status === 403) {
      console.warn('Authentication required, redirecting to login...');
      handleAuthError(error.response.status);
    } else if (error.response?.status === 500) {
      console.error('Server Error:', error.response.data);
    }
    
    return Promise.reject(error);
  }
);

// API functions
export const api = {
  // Get daily runs summary
  getDailyRuns: async (daysBack: number = 30): Promise<DailyRunSummary[]> => {
    const response = await apiClient.get(`/metrics/daily-runs?days_back=${daysBack}`);
    return response.data;
  },

  // Get workflow states distribution
  getWorkflowStates: async (daysBack: number = 7): Promise<WorkflowStateDistribution> => {
    const response = await apiClient.get(`/metrics/workflow-states?days_back=${daysBack}`);
    return response.data;
  },

  // Get configuration metrics
  getConfigurationMetrics: async (daysBack: number = 30): Promise<ConfigurationMetrics[]> => {
    const response = await apiClient.get(`/metrics/configurations?days_back=${daysBack}`);
    return response.data;
  },

  // Get recent failures
  getRecentFailures: async (limit: number = 50): Promise<RecentFailure[]> => {
    const response = await apiClient.get(`/metrics/recent-failures?limit=${limit}`);
    return response.data;
  },

  // Get processing time trends
  getProcessingTimeTrends: async (daysBack: number = 30): Promise<ProcessingTimeTrend[]> => {
    const response = await apiClient.get(`/metrics/processing-times?days_back=${daysBack}`);
    return response.data;
  },

  // Get active configurations
  getActiveConfigurations: async (): Promise<ActiveConfiguration[]> => {
    const response = await apiClient.get('/metrics/active-configurations');
    return response.data;
  },

  // Get system health metrics
  getSystemHealth: async (): Promise<SystemHealthMetrics> => {
    const response = await apiClient.get('/metrics/system-health');
    return response.data;
  },

  // Get all dashboard metrics
  getDashboardMetrics: async (daysBack: number = 30): Promise<DashboardMetrics> => {
    const response = await apiClient.get(`/metrics/dashboard?days_back=${daysBack}`);
    return response.data;
  },

  // Clear cache
  clearCache: async (): Promise<void> => {
    await apiClient.post('/metrics/cache/clear');
  },

  // Health check
  healthCheck: async (): Promise<{ status: string; service: string }> => {
    const response = await apiClient.get('/health');
    return response.data;
  },
};