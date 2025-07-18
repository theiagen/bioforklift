<script lang="ts">
  import { onMount } from 'svelte';
  import Chart from 'chart.js/auto';
  import type { DailyRunSummary } from '$lib/api';
  
  export let dailyRuns: DailyRunSummary[];
  
  let chartCanvas: HTMLCanvasElement;
  let chart: Chart | null = null;
  
  // Chart.js auto import includes all components
  
  function createChart() {
    if (!chartCanvas || !dailyRuns.length) return;
    
    // Destroy existing chart
    if (chart) {
      chart.destroy();
    }
    
    // Sort data by date (oldest first for chart)
    const sortedData = [...dailyRuns].sort((a, b) => 
      new Date(a.date).getTime() - new Date(b.date).getTime()
    );
    
    const labels = sortedData.map(run => 
      new Date(run.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    );
    
    chart = new Chart(chartCanvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Total Runs',
            data: sortedData.map(run => run?.total_runs || 0),
            borderColor: 'rgb(59, 130, 246)',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            tension: 0.4,
            fill: true
          },
          {
            label: 'Successful',
            data: sortedData.map(run => run.successful_runs),
            borderColor: 'rgb(34, 197, 94)',
            backgroundColor: 'rgba(34, 197, 94, 0.1)',
            tension: 0.4
          },
          {
            label: 'Failed',
            data: sortedData.map(run => run?.failed_runs || 0),
            borderColor: 'rgb(239, 68, 68)',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            tension: 0.4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: false
          },
          legend: {
            position: 'top'
          },
          tooltip: {
            mode: 'index',
            intersect: false,
            callbacks: {
              afterBody: function(context) {
                const dataIndex = context[0].dataIndex;
                const run = sortedData[dataIndex];
                return `Success Rate: ${(run?.success_rate || 0).toFixed(1)}%`;
              }
            }
          }
        },
        scales: {
          x: {
            display: true,
            title: {
              display: true,
              text: 'Date'
            }
          },
          y: {
            display: true,
            title: {
              display: true,
              text: 'Number of Runs'
            },
            beginAtZero: true
          }
        },
        interaction: {
          mode: 'nearest',
          axis: 'x',
          intersect: false
        }
      }
    });
  }
  
  onMount(() => {
    createChart();
  });
  
  $: if (dailyRuns && chartCanvas) {
    createChart();
  }
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Daily Runs Trend</h3>
    <div class="text-sm text-gray-600">
      {dailyRuns.length} days of data
    </div>
  </div>
  
  <div class="chart-container">
    <canvas bind:this={chartCanvas}></canvas>
  </div>
  
  <!-- Summary stats -->
  {#if dailyRuns.length > 0}
    {@const totalRuns = dailyRuns.reduce((sum, run) => sum + (run?.total_runs || 0), 0)}
    {@const avgSuccessRate = dailyRuns.reduce((sum, run) => sum + (run?.success_rate || 0), 0) / dailyRuns.length}
    
    <div class="mt-4 grid grid-cols-2 gap-4 text-center">
      <div>
        <div class="text-xl font-semibold text-primary-600">{totalRuns.toLocaleString()}</div>
        <div class="text-sm text-gray-600">Total Runs</div>
      </div>
      <div>
        <div class="text-xl font-semibold text-green-600">{avgSuccessRate.toFixed(1)}%</div>
        <div class="text-sm text-gray-600">Avg Success Rate</div>
      </div>
    </div>
  {/if}
</div>