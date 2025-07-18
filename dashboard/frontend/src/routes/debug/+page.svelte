<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  
  let apiStatus = 'Testing...';
  let dashboardData = null;
  let error = null;
  let logs = [];
  
  function addLog(message) {
    logs = [...logs, `${new Date().toLocaleTimeString()}: ${message}`];
    console.log(message);
  }
  
  onMount(async () => {
    addLog('Starting API tests...');
    
    try {
      // Test individual endpoints
      addLog('Testing system health...');
      const health = await api.getSystemHealth();
      addLog(`✅ System health loaded: ${health.samples_last_24h} samples`);
      
      addLog('Testing daily runs...');
      const dailyRuns = await api.getDailyRuns(7);
      addLog(`✅ Daily runs loaded: ${dailyRuns.length} days`);
      
      addLog('Testing workflow states...');
      const workflowStates = await api.getWorkflowStates();
      addLog(`✅ Workflow states loaded: ${workflowStates.total_workflows} total`);
      
      addLog('Testing full dashboard...');
      dashboardData = await api.getDashboardMetrics(30);
      addLog(`✅ Dashboard data loaded successfully`);
      
      apiStatus = 'All API endpoints working! 🎉';
      
    } catch (err) {
      console.error('API test failed:', err);
      error = err.message || err.toString();
      apiStatus = 'API test failed ❌';
      addLog(`❌ Error: ${error}`);
    }
  });
</script>

<div style="padding: 20px; font-family: monospace;">
  <h1>🔧 Dashboard API Debug</h1>
  
  <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0;">
    <strong>Status:</strong> {apiStatus}
  </div>
  
  {#if error}
    <div style="background: #fee; padding: 15px; border: 1px solid red; border-radius: 5px; margin: 10px 0;">
      <strong>Error:</strong> {error}
    </div>
  {/if}
  
  <h2>📋 API Test Log</h2>
  <div style="background: #000; color: #0f0; padding: 15px; border-radius: 5px; height: 200px; overflow-y: auto; font-family: monospace;">
    {#each logs as log}
      <div>{log}</div>
    {/each}
  </div>
  
  {#if dashboardData}
    <h2>📊 Dashboard Data Preview</h2>
    <div style="background: #e7f5e7; padding: 15px; border-radius: 5px; margin: 10px 0;">
      <p><strong>Daily Runs:</strong> {dashboardData.daily_runs.length} days</p>
      <p><strong>Configurations:</strong> {dashboardData.configuration_metrics.length}</p>
      <p><strong>Recent Failures:</strong> {dashboardData.recent_failures.length}</p>
      <p><strong>Workflow States:</strong> {Object.keys(dashboardData.workflow_distribution.workflow_states).join(', ')}</p>
      <p><strong>System Health - 24h Samples:</strong> {dashboardData.system_health.samples_last_24h}</p>
      <p><strong>Success Rate:</strong> {dashboardData.system_health.success_rate_24h}%</p>
    </div>
    
    <details>
      <summary>🔍 Raw Data (Click to expand)</summary>
      <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 400px; overflow-y: auto;">
{JSON.stringify(dashboardData, null, 2)}
      </pre>
    </details>
  {/if}
  
  <h2>🔗 Useful Links</h2>
  <div style="margin: 20px 0;">
    <a href="/" style="margin-right: 15px; color: blue;">← Back to Dashboard</a>
    <a href="http://localhost:8000/docs" target="_blank" style="margin-right: 15px; color: blue;">API Docs</a>
    <a href="http://localhost:8000/health" target="_blank" style="color: blue;">Health Check</a>
  </div>
</div>