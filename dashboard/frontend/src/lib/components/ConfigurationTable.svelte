<script lang="ts">
  import type { ConfigurationMetrics } from '$lib/api';
  
  export let configurations: ConfigurationMetrics[];
  
  let sortColumn: keyof ConfigurationMetrics = 'total_samples';
  let sortDirection: 'asc' | 'desc' = 'desc';
  
  function sortTable(column: keyof ConfigurationMetrics) {
    if (sortColumn === column) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = column;
      sortDirection = 'desc';
    }
  }
  
  $: sortedConfigurations = [...configurations].sort((a, b) => {
    const aValue = a[sortColumn];
    const bValue = b[sortColumn];
    
    if (aValue === null && bValue === null) return 0;
    if (aValue === null) return 1;
    if (bValue === null) return -1;
    
    const comparison = aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
    return sortDirection === 'asc' ? comparison : -comparison;
  });
  
  function getSuccessRateColor(rate: number): string {
    if (rate >= 90) return 'text-green-600';
    if (rate >= 70) return 'text-yellow-600';
    return 'text-red-600';
  }
  
  function formatProcessingTime(minutes: number | null): string {
    if (minutes === null) return 'N/A';
    if (minutes < 60) return `${minutes.toFixed(1)}m`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes.toFixed(0)}m`;
  }
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Configuration Performance</h3>
    <div class="text-sm text-gray-600">
      {configurations.length} configurations
    </div>
  </div>
  
  <div class="overflow-x-auto">
    <table class="min-w-full divide-y divide-gray-200">
      <thead class="bg-gray-50">
        <tr>
          <th 
            class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            on:click={() => sortTable('config_name')}
          >
            <div class="flex items-center space-x-1">
              <span>Configuration</span>
              {#if sortColumn === 'config_name'}
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {#if sortDirection === 'asc'}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l4-4 4 4m0 6l-4 4-4-4"></path>
                  {:else}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 15l-4 4-4-4m0-6l4-4 4 4"></path>
                  {/if}
                </svg>
              {/if}
            </div>
          </th>
          <th 
            class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            on:click={() => sortTable('total_samples')}
          >
            <div class="flex items-center space-x-1">
              <span>Total Samples</span>
              {#if sortColumn === 'total_samples'}
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {#if sortDirection === 'asc'}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l4-4 4 4m0 6l-4 4-4-4"></path>
                  {:else}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 15l-4 4-4-4m0-6l4-4 4 4"></path>
                  {/if}
                </svg>
              {/if}
            </div>
          </th>
          <th 
            class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            on:click={() => sortTable('success_rate')}
          >
            <div class="flex items-center space-x-1">
              <span>Success Rate</span>
              {#if sortColumn === 'success_rate'}
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {#if sortDirection === 'asc'}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l4-4 4 4m0 6l-4 4-4-4"></path>
                  {:else}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 15l-4 4-4-4m0-6l4-4 4 4"></path>
                  {/if}
                </svg>
              {/if}
            </div>
          </th>
          <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
            Success/Failed
          </th>
          <th 
            class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
            on:click={() => sortTable('avg_processing_time_minutes')}
          >
            <div class="flex items-center space-x-1">
              <span>Avg Processing Time</span>
              {#if sortColumn === 'avg_processing_time_minutes'}
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {#if sortDirection === 'asc'}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l4-4 4 4m0 6l-4 4-4-4"></path>
                  {:else}
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 15l-4 4-4-4m0-6l4-4 4 4"></path>
                  {/if}
                </svg>
              {/if}
            </div>
          </th>
        </tr>
      </thead>
      <tbody class="bg-white divide-y divide-gray-200">
        {#each sortedConfigurations as config}
          <tr class="hover:bg-gray-50">
            <td class="px-6 py-4 whitespace-nowrap">
              <div>
                <div class="text-sm font-medium text-gray-900">
                  {config.config_name || 'Unknown'}
                </div>
                <div class="text-sm text-gray-500">
                  {config.config_id}
                </div>
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
              {config.total_samples.toLocaleString()}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="flex items-center">
                <span class="text-sm font-medium {getSuccessRateColor(config.success_rate)}">
                  {config.success_rate.toFixed(1)}%
                </span>
                <div class="ml-2 w-16 bg-gray-200 rounded-full h-2">
                  <div 
                    class="h-2 rounded-full {config.success_rate >= 90 ? 'bg-green-600' : config.success_rate >= 70 ? 'bg-yellow-600' : 'bg-red-600'}"
                    style="width: {config.success_rate}%"
                  ></div>
                </div>
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
              <span class="text-green-600">{config.successful_samples}</span>
              /
              <span class="text-red-600">{config.failed_samples}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
              {formatProcessingTime(config.avg_processing_time_minutes)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  
  {#if configurations.length === 0}
    <div class="text-center py-8 text-gray-500">
      No configuration data available
    </div>
  {/if}
</div>