<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  
  let step = 1;
  let loading = true;
  let error = null;
  let dashboardData = null;
  let logs = [];
  
  function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    logs = [...logs, { timestamp, message, type }];
    console.log(`[${timestamp}] ${message}`);
  }
  
  onMount(async () => {
    try {
      addLog('🚀 Starting dashboard data load...');
      step = 1;
      
      addLog('📡 Calling api.getDashboardMetrics(30)...');
      step = 2;
      
      // This is the exact same call the main dashboard makes
      dashboardData = await api.getDashboardMetrics(30);
      step = 3;
      
      addLog('✅ Dashboard data received', 'success');
      addLog(`📊 Data structure: ${Object.keys(dashboardData).join(', ')}`, 'success');
      addLog(`📈 Daily runs: ${dashboardData.daily_runs?.length || 0} days`, 'success');
      addLog(`⚙️ Configurations: ${dashboardData.configuration_metrics?.length || 0}`, 'success');
      addLog(`❌ Recent failures: ${dashboardData.recent_failures?.length || 0}`, 'success');
      addLog(`💚 System health samples: ${dashboardData.system_health?.samples_last_24h || 0}`, 'success');
      
      step = 4;
      loading = false;
      
    } catch (err) {
      addLog(`❌ Error at step ${step}: ${err.message}`, 'error');
      error = err.message;
      loading = false;
    }
  });
</script>

<div style="padding: 20px; font-family: monospace; max-width: 1200px; margin: 0 auto;">
  <h1>🔍 Step-by-Step Dashboard Debug</h1>
  
  <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
    <strong>Current Step:</strong> {step}/4
    <br>
    <strong>Status:</strong> {loading ? 'Loading...' : error ? 'Error' : 'Complete'}
  </div>
  
  <div style="background: #000; color: #0f0; padding: 15px; border-radius: 5px; height: 300px; overflow-y: auto; margin: 20px 0;">
    <div style="color: #fff; margin-bottom: 10px;"><strong>Debug Log:</strong></div>
    {#each logs as log}
      <div style="color: {log.type === 'error' ? '#ff6b6b' : log.type === 'success' ? '#51cf66' : '#0ff'};">
        [{log.timestamp}] {log.message}
      </div>
    {/each}
  </div>
  
  {#if error}
    <div style="background: #fee; border: 1px solid red; padding: 15px; border-radius: 5px; margin: 20px 0;">
      <strong>❌ Error Details:</strong><br>
      {error}
    </div>
  {/if}
  
  {#if dashboardData && !loading}
    <div style="background: #e7f5e7; border: 1px solid green; padding: 15px; border-radius: 5px; margin: 20px 0;">
      <h2>✅ Data Successfully Loaded</h2>
      
      <h3>📊 Data Summary:</h3>
      <ul>
        <li><strong>Daily Runs:</strong> {dashboardData.daily_runs?.length || 0} days</li>
        <li><strong>System Health - 24h Samples:</strong> {dashboardData.system_health?.samples_last_24h || 0}</li>
        <li><strong>System Health - Success Rate:</strong> {dashboardData.system_health?.success_rate_24h || 0}%</li>
        <li><strong>Workflow States:</strong> {Object.keys(dashboardData.workflow_distribution?.workflow_states || {}).length} states</li>
        <li><strong>Configuration Metrics:</strong> {dashboardData.configuration_metrics?.length || 0} configs</li>
        <li><strong>Recent Failures:</strong> {dashboardData.recent_failures?.length || 0} failures</li>
        <li><strong>Processing Trends:</strong> {dashboardData.processing_trends?.length || 0} data points</li>
        <li><strong>Active Configurations:</strong> {dashboardData.active_configurations?.length || 0} configs</li>
      </ul>
      
      <h3>🔍 Sample Daily Run Data:</h3>
      {#if dashboardData.daily_runs && dashboardData.daily_runs.length > 0}
        <pre style="background: #f8f9fa; padding: 10px; border-radius: 5px; overflow-x: auto;">
{JSON.stringify(dashboardData.daily_runs[0], null, 2)}
        </pre>
      {/if}
      
      <h3>🔍 Sample System Health Data:</h3>
      {#if dashboardData.system_health}
        <pre style="background: #f8f9fa; padding: 10px; border-radius: 5px; overflow-x: auto;">
{JSON.stringify(dashboardData.system_health, null, 2)}
        </pre>
      {/if}
      
      <details style="margin: 20px 0;">
        <summary style="cursor: pointer; padding: 10px; background: #f0f0f0; border-radius: 5px;">
          🔍 Full Raw Data (Click to expand)
        </summary>
        <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 400px; overflow-y: auto; margin-top: 10px;">
{JSON.stringify(dashboardData, null, 2)}
        </pre>
      </details>
    </div>
    
    <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
      <h3>🎯 Next Steps:</h3>
      <p>Since the data is loading successfully here, the issue is likely in:</p>
      <ol>
        <li><strong>Component Rendering:</strong> One of the dashboard components is failing silently</li>
        <li><strong>Chart.js Integration:</strong> Charts might still have issues even after the import fix</li>
        <li><strong>CSS/Layout Issues:</strong> Components might be rendering but hidden</li>
        <li><strong>Data Binding:</strong> Props might not be passed correctly to child components</li>
      </ol>
      
      <p><strong>🔍 Check browser console on the main dashboard for JavaScript errors!</strong></p>
    </div>
  {/if}
  
  <div style="margin: 20px 0; text-align: center;">
    <a href="/" style="margin-right: 15px; color: blue; text-decoration: none;">← Back to Main Dashboard</a>
    <a href="/simple" style="margin-right: 15px; color: blue; text-decoration: none;">Simple Dashboard</a>
    <a href="/debug" style="color: blue; text-decoration: none;">API Debug</a>
  </div>
</div>