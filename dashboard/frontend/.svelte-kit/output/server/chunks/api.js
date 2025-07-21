import axios from "axios";
function redirectToLogin() {
  window.location.href = "/auth/login";
}
function handleAuthError(status) {
  if (status === 401 || status === 403) {
    redirectToLogin();
  }
}
const API_BASE_URL = "http://localhost:8000/api/v1";
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 3e4,
  headers: {
    "Content-Type": "application/json"
  },
  withCredentials: true
  // Include cookies for session management
});
apiClient.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error("API Request Error:", error);
    return Promise.reject(error);
  }
);
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error("API Response Error:", error);
    if (error.response?.status === 401 || error.response?.status === 403) {
      console.warn("Authentication required, redirecting to login...");
      handleAuthError(error.response.status);
    } else if (error.response?.status === 500) {
      console.error("Server Error:", error.response.data);
    }
    return Promise.reject(error);
  }
);
const api = {
  // Get daily runs summary
  getDailyRuns: async (daysBack = 30) => {
    const response = await apiClient.get(`/metrics/daily-runs?days_back=${daysBack}`);
    return response.data;
  },
  // Get workflow states distribution
  getWorkflowStates: async (daysBack = 7) => {
    const response = await apiClient.get(`/metrics/workflow-states?days_back=${daysBack}`);
    return response.data;
  },
  // Get configuration metrics
  getConfigurationMetrics: async (daysBack = 30) => {
    const response = await apiClient.get(`/metrics/configurations?days_back=${daysBack}`);
    return response.data;
  },
  // Get recent failures
  getRecentFailures: async (limit = 50) => {
    const response = await apiClient.get(`/metrics/recent-failures?limit=${limit}`);
    return response.data;
  },
  // Get processing time trends
  getProcessingTimeTrends: async (daysBack = 30) => {
    const response = await apiClient.get(`/metrics/processing-times?days_back=${daysBack}`);
    return response.data;
  },
  // Get active configurations
  getActiveConfigurations: async () => {
    const response = await apiClient.get("/metrics/active-configurations");
    return response.data;
  },
  // Get system health metrics
  getSystemHealth: async () => {
    const response = await apiClient.get("/metrics/system-health");
    return response.data;
  },
  // Get all dashboard metrics
  getDashboardMetrics: async (daysBack = 30) => {
    const response = await apiClient.get(`/metrics/dashboard?days_back=${daysBack}`);
    return response.data;
  },
  // Clear cache
  clearCache: async () => {
    await apiClient.post("/metrics/cache/clear");
  },
  // Health check
  healthCheck: async () => {
    const response = await apiClient.get("/health");
    return response.data;
  }
};
export {
  api as a
};
