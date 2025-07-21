<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type DashboardMetrics } from '$lib/api';
  import SystemHealthCard from '$lib/components/SystemHealthCard.svelte';
  import DailyRunsChart from '$lib/components/DailyRunsChart.svelte';
  import WorkflowDistribution from '$lib/components/WorkflowDistribution.svelte';
  import ConfigurationTable from '$lib/components/ConfigurationTable.svelte';
  import RecentFailures from '$lib/components/RecentFailures.svelte';
  import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
  import ErrorCard from '$lib/components/ErrorCard.svelte';
  
  let dashboardData: DashboardMetrics | null = null;
  let loading = true;
  let error: string | null = null;
  let lastRefresh = new Date();
  let daysBack = 30;
  let customDaysInput = '';
  let showCustomInput = false;
  
  async function loadDashboardData() {
    try {
      loading = true;
      error = null;
      
      dashboardData = await api.getDashboardMetrics(daysBack);
      lastRefresh = new Date();
      console.log('✅ Dashboard data loaded successfully:', dashboardData);
      console.log('📊 Daily runs:', dashboardData?.daily_runs?.length);
      console.log('💚 System health:', dashboardData?.system_health);
      console.log('🔄 Workflow distribution:', dashboardData?.workflow_distribution);
    } catch (err) {
      console.error('Error loading dashboard data:', err);
      error = 'Failed to load dashboard data. Please check your connection and try again.';
    } finally {
      loading = false;
    }
  }
  
  async function refreshData() {
    await loadDashboardData();
  }

  function setDaysBack(days: number) {
    daysBack = days;
    showCustomInput = false;
    customDaysInput = '';
  }

  function toggleCustomInput() {
    showCustomInput = !showCustomInput;
    if (showCustomInput) {
      customDaysInput = daysBack.toString();
    }
  }

  function applyCustomDays() {
    const customDays = parseInt(customDaysInput);
    if (!isNaN(customDays) && customDays > 0 && customDays <= 365) {
      daysBack = customDays;
      showCustomInput = false;
    }
  }

  function handleCustomKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      applyCustomDays();
    } else if (event.key === 'Escape') {
      showCustomInput = false;
      customDaysInput = '';
    }
  }
  
  let previousDaysBack = daysBack;
  
  onMount(() => {
    loadDashboardData();
    
    // Auto-refresh every 5 minutes
    const interval = setInterval(loadDashboardData, 5 * 60 * 1000);
    
    return () => clearInterval(interval);
  });
  
  $: {
    // Only reload when daysBack changes after mount, not during SSR
    if (typeof window !== 'undefined' && daysBack !== previousDaysBack) {
      previousDaysBack = daysBack;
      loadDashboardData();
    }
  }
</script>

<div class="space-y-6">
  <!-- Header Controls -->
  <div class="flex justify-between items-center">
    <div>
      <h2 class="text-2xl font-bold text-gray-900">Dashboard Overview</h2>
      <p class="text-gray-600 mt-1">
        Last updated: {lastRefresh.toLocaleString()}
      </p>
    </div>
    <div class="flex items-center space-x-4">
      <div class="flex items-center space-x-2">
        <span class="text-sm font-medium text-gray-700">
          Time period:
        </span>
        
        <!-- Preset buttons -->
        <div class="flex space-x-1">
          <button
            on:click={() => setDaysBack(7)}
            class="px-3 py-1 text-sm rounded-md transition-colors {daysBack === 7 ? 'bg-primary-100 text-primary-800 border border-primary-300' : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'}"
          >
            7d
          </button>
          <button
            on:click={() => setDaysBack(30)}
            class="px-3 py-1 text-sm rounded-md transition-colors {daysBack === 30 ? 'bg-primary-100 text-primary-800 border border-primary-300' : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'}"
          >
            30d
          </button>
          <button
            on:click={() => setDaysBack(90)}
            class="px-3 py-1 text-sm rounded-md transition-colors {daysBack === 90 ? 'bg-primary-100 text-primary-800 border border-primary-300' : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'}"
          >
            90d
          </button>
          <button
            on:click={toggleCustomInput}
            class="px-3 py-1 text-sm rounded-md transition-colors {showCustomInput || ![7, 30, 90].includes(daysBack) ? 'bg-primary-100 text-primary-800 border border-primary-300' : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'}"
          >
            {![7, 30, 90].includes(daysBack) ? `${daysBack}d` : 'Custom'}
          </button>
        </div>
        
        <!-- Custom input field -->
        {#if showCustomInput}
          <div class="flex items-center space-x-1">
            <input
              type="number"
              bind:value={customDaysInput}
              on:keydown={handleCustomKeydown}
              placeholder="Days"
              min="1"
              max="365"
              class="w-16 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <button
              on:click={applyCustomDays}
              class="px-2 py-1 text-sm bg-primary-600 text-white rounded-md hover:bg-primary-700"
            >
              ✓
            </button>
            <button
              on:click={() => showCustomInput = false}
              class="px-2 py-1 text-sm bg-gray-400 text-white rounded-md hover:bg-gray-500"
            >
              ✕
            </button>
          </div>
        {/if}
      </div>
      <button
        on:click={refreshData}
        disabled={loading}
        class="bg-primary-600 text-white px-4 py-2 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
        </svg>
        <span>Refresh</span>
      </button>
    </div>
  </div>

  {#if loading}
    <div class="flex justify-center items-center h-64">
      <LoadingSpinner />
    </div>
  {:else if error}
    <ErrorCard {error} on:retry={refreshData} />
  {:else if dashboardData}
    <!-- System Health Overview -->
    <SystemHealthCard systemHealth={dashboardData.system_health} />
    
    <!-- Charts Row -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <DailyRunsChart dailyRuns={dashboardData.daily_runs} />
      <WorkflowDistribution workflowDistribution={dashboardData.workflow_distribution} />
    </div>
    
    <!-- Configuration Metrics -->
    <ConfigurationTable configurations={dashboardData.configuration_metrics} />
    
    <!-- Recent Failures -->
    <RecentFailures failures={dashboardData.recent_failures} />
  {/if}
</div>