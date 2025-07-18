<script lang="ts">
  import type { SystemHealthMetrics } from '$lib/api';
  
  export let systemHealth: SystemHealthMetrics;
  
  $: successRate = systemHealth?.success_rate_24h || 0;
  $: healthStatus = successRate >= 90 ? 'healthy' : 
                   successRate >= 70 ? 'warning' : 'critical';
  
  $: statusColor = healthStatus === 'healthy' ? 'green' : 
                   healthStatus === 'warning' ? 'yellow' : 'red';
</script>

<div class="card">
  <div class="card-header">
    <h2 class="card-title">System Health Overview</h2>
    <div class="flex items-center space-x-2">
      <div class="h-3 w-3 bg-{statusColor}-500 rounded-full"></div>
      <span class="text-sm font-medium text-{statusColor}-700 capitalize">{healthStatus}</span>
    </div>
  </div>
  
  <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
    <div class="text-center">
      <div class="metric-value">{(systemHealth?.samples_last_24h || 0).toLocaleString()}</div>
      <div class="metric-label">Samples (24h)</div>
    </div>
    
    <div class="text-center">
      <div class="metric-value text-green-600">{(systemHealth?.successful_last_24h || 0).toLocaleString()}</div>
      <div class="metric-label">Successful</div>
    </div>
    
    <div class="text-center">
      <div class="metric-value text-red-600">{(systemHealth?.failed_last_24h || 0).toLocaleString()}</div>
      <div class="metric-label">Failed</div>
    </div>
    
    <div class="text-center">
      <div class="metric-value text-blue-600">{(systemHealth?.currently_in_progress || 0).toLocaleString()}</div>
      <div class="metric-label">In Progress</div>
    </div>
    
    <div class="text-center">
      <div class="metric-value text-{statusColor}-600">{successRate.toFixed(1)}%</div>
      <div class="metric-label">Success Rate</div>
    </div>
  </div>
  
  <!-- Progress bars -->
  <div class="mt-6 space-y-3">
    <div>
      <div class="flex justify-between text-sm text-gray-600 mb-1">
        <span>Success Rate (24h)</span>
        <span>{successRate.toFixed(1)}%</span>
      </div>
      <div class="w-full bg-gray-200 rounded-full h-2">
        <div 
          class="bg-{statusColor}-600 h-2 rounded-full transition-all duration-300"
          style="width: {successRate}%"
        ></div>
      </div>
    </div>
    
    {#if systemHealth?.failure_rate_24h && systemHealth.failure_rate_24h > 0}
      {@const failureRate = systemHealth.failure_rate_24h}
      <div>
        <div class="flex justify-between text-sm text-gray-600 mb-1">
          <span>Failure Rate (24h)</span>
          <span>{failureRate.toFixed(1)}%</span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div 
            class="bg-red-600 h-2 rounded-full transition-all duration-300"
            style="width: {failureRate}%"
          ></div>
        </div>
      </div>
    {/if}
  </div>
</div>