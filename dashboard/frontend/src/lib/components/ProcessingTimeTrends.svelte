<script lang="ts">
  import { onMount } from 'svelte';
  import Chart from 'chart.js/auto';
  import type { ProcessingTimeTrend } from '$lib/api';
  
  export let processingTrends: ProcessingTimeTrend[];
  
  let chartCanvas: HTMLCanvasElement;
  let chart: Chart | null = null;
  
  // Chart.js auto import includes all components
  
  function createChart() {
    if (!chartCanvas || !processingTrends.length) return;
    
    // Destroy existing chart
    if (chart) {
      chart.destroy();
    }
    
    // Sort data by date (oldest first for chart)
    const sortedData = [...processingTrends]
      .filter(trend => trend.avg_processing_time_minutes !== null)
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    
    if (sortedData.length === 0) return;
    
    const labels = sortedData.map(trend => 
      new Date(trend.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    );
    
    chart = new Chart(chartCanvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Avg Processing Time (minutes)',
            data: sortedData.map(trend => trend.avg_processing_time_minutes),
            borderColor: 'rgb(139, 92, 246)',
            backgroundColor: 'rgba(139, 92, 246, 0.1)',
            tension: 0.4,
            fill: true,
            yAxisID: 'y'
          },
          {
            label: 'Sample Count',
            data: sortedData.map(trend => trend.sample_count),
            borderColor: 'rgb(34, 197, 94)',
            backgroundColor: 'rgba(34, 197, 94, 0.1)',
            tension: 0.4,
            type: 'bar',
            yAxisID: 'y1'
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
              label: function(context) {
                if (context.datasetIndex === 0) {
                  const minutes = context.parsed.y;
                  if (minutes < 60) {
                    return `Processing Time: ${minutes.toFixed(1)} minutes`;
                  } else {
                    const hours = Math.floor(minutes / 60);
                    const remainingMinutes = minutes % 60;
                    return `Processing Time: ${hours}h ${remainingMinutes.toFixed(0)}m`;
                  }
                } else {
                  return `Sample Count: ${context.parsed.y}`;
                }
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
            type: 'linear',
            display: true,
            position: 'left',
            title: {
              display: true,
              text: 'Processing Time (minutes)'
            },
            beginAtZero: true
          },
          y1: {
            type: 'linear',
            display: true,
            position: 'right',
            title: {
              display: true,
              text: 'Sample Count'
            },
            beginAtZero: true,
            grid: {
              drawOnChartArea: false,
            },
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
  
  $: if (processingTrends && chartCanvas) {
    createChart();
  }
  
  function formatProcessingTime(minutes: number | null): string {
    if (minutes === null) return 'N/A';
    if (minutes < 60) return `${minutes.toFixed(1)}m`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes.toFixed(0)}m`;
  }
  
  $: validTrends = processingTrends.filter(trend => trend.avg_processing_time_minutes !== null);
  $: avgProcessingTime = validTrends.length > 0 
    ? validTrends.reduce((sum, trend) => sum + (trend.avg_processing_time_minutes || 0), 0) / validTrends.length
    : null;
  $: totalSamples = processingTrends.reduce((sum, trend) => sum + trend.sample_count, 0);
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Processing Time Trends</h3>
    <div class="text-sm text-gray-600">
      {processingTrends.length} days of data
    </div>
  </div>
  
  {#if validTrends.length === 0}
    <div class="text-center py-8 text-gray-500">
      <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
      </svg>
      <p class="mt-2">No processing time data available</p>
    </div>
  {:else}
    <div class="chart-container">
      <canvas bind:this={chartCanvas}></canvas>
    </div>
    
    <!-- Summary stats -->
    <div class="mt-4 grid grid-cols-2 gap-4 text-center">
      <div>
        <div class="text-xl font-semibold text-purple-600">
          {formatProcessingTime(avgProcessingTime)}
        </div>
        <div class="text-sm text-gray-600">Avg Processing Time</div>
      </div>
      <div>
        <div class="text-xl font-semibold text-green-600">{totalSamples.toLocaleString()}</div>
        <div class="text-sm text-gray-600">Total Samples Processed</div>
      </div>
    </div>
  {/if}
</div>