<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type DashboardMetrics } from '$lib/api';
  import SystemHealthCard from '$lib/components/SystemHealthCard.svelte';
  import DailyRunsChart from '$lib/components/DailyRunsChart.svelte';
  import WorkflowDistribution from '$lib/components/WorkflowDistribution.svelte';
  import ConfigurationTable from '$lib/components/ConfigurationTable.svelte';
  import RecentFailures from '$lib/components/RecentFailures.svelte';
  import ProcessingTimeTrends from '$lib/components/ProcessingTimeTrends.svelte';
  import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
  import ErrorCard from '$lib/components/ErrorCard.svelte';
  
  let dashboardData: DashboardMetrics | null = null;
  let loading = true;
  let error: string | null = null;
  let lastRefresh = new Date();
  let daysBack = 30;
  
  async function loadDashboardData() {
    try {
      loading = true;
      error = null;
      
      dashboardData = await api.getDashboardMetrics(daysBack);
      lastRefresh = new Date();
      console.log('✅ Dashboard data loaded successfully:', dashboardData);
      console.log('📊 Daily runs:', dashboardData?.daily_runs?.length);
      console.log('💚 System health:', dashboardData?.system_health);
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
        <label for="days-back" class="text-sm font-medium text-gray-700">
          Days back:
        </label>
        <select
          id="days-back"
          bind:value={daysBack}
          class="border border-gray-300 rounded-md px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
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
    
    <!-- Processing Time Trends -->
    <ProcessingTimeTrends processingTrends={dashboardData.processing_trends} />
    
    <!-- Configuration Metrics -->
    <ConfigurationTable configurations={dashboardData.configuration_metrics} />
    
    <!-- Recent Failures -->
    <RecentFailures failures={dashboardData.recent_failures} />
  {/if}
</div>