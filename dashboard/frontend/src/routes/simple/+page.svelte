<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  
  let loading = true;
  let error = null;
  let systemHealth = null;
  let dailyRuns = [];
  let workflowStates = null;
  
  onMount(async () => {
    try {
      console.log('Loading simple dashboard...');
      
      // Load data step by step
      systemHealth = await api.getSystemHealth();
      console.log('System health loaded:', systemHealth);
      
      dailyRuns = await api.getDailyRuns(7);
      console.log('Daily runs loaded:', dailyRuns);
      
      workflowStates = await api.getWorkflowStates();
      console.log('Workflow states loaded:', workflowStates);
      
      loading = false;
      console.log('Simple dashboard loaded successfully');
      
    } catch (err) {
      console.error('Simple dashboard error:', err);
      error = err.message;
      loading = false;
    }
  });
</script>

<div style="padding: 20px; font-family: sans-serif;">
  <h1>🧬 Simple Dashboard Test</h1>
  
  {#if loading}
    <div style="text-align: center; padding: 40px;">
      <div style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 2s linear infinite; margin: 0 auto;"></div>
      <p>Loading...</p>
    </div>
  {:else if error}
    <div style="background: #fee; border: 1px solid red; padding: 15px; border-radius: 5px;">
      <strong>Error:</strong> {error}
    </div>
  {:else}
    <!-- System Health -->
    {#if systemHealth}
      <div style="background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h2>System Health (24h)</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
          <div style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">{systemHealth.samples_last_24h}</div>
            <div style="font-size: 14px; color: #666;">Total Samples</div>
          </div>
          <div style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold; color: #22c55e;">{systemHealth.successful_last_24h}</div>
            <div style="font-size: 14px; color: #666;">Successful</div>
          </div>
          <div style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold; color: #ef4444;">{systemHealth.failed_last_24h}</div>
            <div style="font-size: 14px; color: #666;">Failed</div>
          </div>
          <div style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold; color: #f59e0b;">{systemHealth.currently_in_progress}</div>
            <div style="font-size: 14px; color: #666;">In Progress</div>
          </div>
          <div style="text-align: center;">
            <div style="font-size: 24px; font-weight: bold; color: #8b5cf6;">{systemHealth.success_rate_24h}%</div>
            <div style="font-size: 14px; color: #666;">Success Rate</div>
          </div>
        </div>
      </div>
    {/if}
    
    <!-- Daily Runs Table -->
    {#if dailyRuns.length > 0}
      <div style="background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h2>Daily Runs (Last 7 Days)</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <thead>
            <tr style="border-bottom: 2px solid #eee;">
              <th style="text-align: left; padding: 10px;">Date</th>
              <th style="text-align: right; padding: 10px;">Total</th>
              <th style="text-align: right; padding: 10px;">Successful</th>
              <th style="text-align: right; padding: 10px;">Failed</th>
              <th style="text-align: right; padding: 10px;">Success Rate</th>
            </tr>
          </thead>
          <tbody>
            {#each dailyRuns as run}
              <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px;">{new Date(run.date).toLocaleDateString()}</td>
                <td style="text-align: right; padding: 10px;">{run.total_runs}</td>
                <td style="text-align: right; padding: 10px; color: #22c55e;">{run.successful_runs}</td>
                <td style="text-align: right; padding: 10px; color: #ef4444;">{run.failed_runs}</td>
                <td style="text-align: right; padding: 10px;">
                  {run.total_runs > 0 ? ((run.successful_runs / run.total_runs) * 100).toFixed(1) : 0}%
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
    
    <!-- Workflow States -->
    {#if workflowStates}
      <div style="background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h2>Workflow States</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px;">
          {#each Object.entries(workflowStates.workflow_states) as [state, count]}
            {@const percentage = ((count / workflowStates.total_workflows) * 100).toFixed(1)}
            {@const color = state === 'Succeeded' ? '#22c55e' : state === 'Failed' ? '#ef4444' : state === 'Running' ? '#3b82f6' : '#6b7280'}
            <div style="text-align: center; padding: 15px; border: 1px solid #eee; border-radius: 5px;">
              <div style="font-size: 20px; font-weight: bold; color: {color};">{count}</div>
              <div style="font-size: 12px; color: #666; margin: 5px 0;">{state}</div>
              <div style="font-size: 11px; color: #999;">{percentage}%</div>
            </div>
          {/each}
        </div>
        <div style="margin-top: 15px; text-align: center; color: #666;">
          Total Workflows: {workflowStates.total_workflows}
        </div>
      </div>
    {/if}
    
  {/if}
  
  <div style="margin: 20px 0; text-align: center;">
    <a href="/" style="margin-right: 15px; color: blue; text-decoration: none;">← Back to Main Dashboard</a>
    <a href="/debug" style="margin-right: 15px; color: blue; text-decoration: none;">Debug Page</a>
    <a href="/test" style="color: blue; text-decoration: none;">API Test</a>
  </div>
</div>

<style>
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
</style>