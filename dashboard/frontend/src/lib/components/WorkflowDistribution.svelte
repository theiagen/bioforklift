<script lang="ts">
  import { onMount } from 'svelte';
  import Chart from 'chart.js/auto';
  import type { WorkflowStateDistribution } from '$lib/api';
  
  export let workflowDistribution: WorkflowStateDistribution;
  
  let chartCanvas: HTMLCanvasElement;
  let chart: Chart | null = null;
  
  // Chart.js auto import includes all components
  
  const stateColors: Record<string, string> = {
    'Succeeded': '#22c55e',
    'Failed': '#ef4444',
    'Aborted': '#f59e0b',
    'Running': '#3b82f6',
    'Queued': '#8b5cf6',
    'Unknown': '#6b7280'
  };
  
  function createChart() {
    console.log('🔍 WorkflowDistribution - createChart called');
    console.log('📊 workflowDistribution:', workflowDistribution);
    console.log('🎯 workflow_states:', workflowDistribution?.workflow_states);
    console.log('🖥️ chartCanvas:', chartCanvas);
    
    if (!chartCanvas || !workflowDistribution?.workflow_states) {
      console.log('❌ Missing chartCanvas or workflow_states - returning early');
      return;
    }
    
    // Destroy existing chart
    if (chart) {
      chart.destroy();
    }
    
    const entries = Object.entries(workflowDistribution.workflow_states || {});
    console.log('📋 entries:', entries);
    if (entries.length === 0) {
      console.log('❌ No entries found - returning early');
      return;
    }
    
    // Sort by count (descending)
    entries.sort((a, b) => b[1] - a[1]);
    
    const labels = entries.map(([state]) => state);
    const data = entries.map(([, count]) => count);
    const colors = labels.map(state => stateColors[state] || stateColors['Unknown']);
    
    chart = new Chart(chartCanvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: colors.map(color => color),
          borderWidth: 2,
          hoverBorderWidth: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right',
            labels: {
              generateLabels: function(chart) {
                const data = chart.data;
                if (data.labels && data.datasets.length) {
                  return data.labels.map((label, i) => {
                    const dataset = data.datasets[0];
                    const value = dataset.data[i] as number;
                    const total = workflowDistribution?.total_workflows || 0;
                    const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
                    
                    return {
                      text: `${label}: ${value} (${percentage}%)`,
                      fillStyle: dataset.backgroundColor![i] as string,
                      hidden: false,
                      index: i
                    };
                  });
                }
                return [];
              }
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                const label = context.label || '';
                const value = context.parsed;
                const total = workflowDistribution?.total_workflows || 0;
                const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
                return `${label}: ${value} (${percentage}%)`;
              }
            }
          }
        },
        cutout: '50%'
      }
    });
  }
  
  onMount(() => {
    createChart();
  });
  
  $: if (workflowDistribution && chartCanvas) {
    createChart();
  }
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Workflow State Distribution</h3>
    <div class="text-sm text-gray-600">
      {(workflowDistribution?.total_workflows || 0).toLocaleString()} total workflows
    </div>
  </div>
  
  <div class="chart-container">
    <canvas bind:this={chartCanvas}></canvas>
  </div>
  
  <!-- State badges -->
  <div class="mt-4 flex flex-wrap gap-2">
    {#each Object.entries(workflowDistribution?.workflow_states || {}) as [state, count]}
      {@const percentage = (workflowDistribution?.total_workflows || 0) > 0 
        ? ((count / (workflowDistribution?.total_workflows || 1)) * 100).toFixed(1) 
        : '0.0'}
      <div class="flex items-center space-x-2 px-3 py-1 rounded-full text-sm"
           style="background-color: {stateColors[state] || stateColors['Unknown']}20; 
                  color: {stateColors[state] || stateColors['Unknown']}">
        <div class="w-2 h-2 rounded-full"
             style="background-color: {stateColors[state] || stateColors['Unknown']}"></div>
        <span class="font-medium">{state}</span>
        <span>{count} ({percentage}%)</span>
      </div>
    {/each}
  </div>
</div>