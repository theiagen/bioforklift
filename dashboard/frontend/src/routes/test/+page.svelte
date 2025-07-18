<script>
  import { onMount } from 'svelte';
  
  let status = 'Loading...';
  let healthData = null;
  let error = null;
  
  onMount(async () => {
    try {
      console.log('Testing API connection...');
      
      // Test basic fetch
      const response = await fetch('http://localhost:8000/health');
      console.log('Health response:', response);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Health data:', data);
      
      status = 'Backend Connected ✅';
      
      // Test metrics endpoint
      const metricsResponse = await fetch('http://localhost:8000/api/v1/metrics/system-health');
      console.log('Metrics response:', metricsResponse);
      
      if (!metricsResponse.ok) {
        throw new Error(`Metrics HTTP ${metricsResponse.status}`);
      }
      
      healthData = await metricsResponse.json();
      console.log('Metrics data:', healthData);
      
    } catch (err) {
      console.error('Error:', err);
      error = err.message;
      status = 'Connection Failed ❌';
    }
  });
</script>

<div style="padding: 20px; font-family: monospace;">
  <h1>API Connection Test</h1>
  
  <p><strong>Status:</strong> {status}</p>
  
  {#if error}
    <div style="background: #fee; padding: 10px; border: 1px solid red;">
      <strong>Error:</strong> {error}
    </div>
  {/if}
  
  {#if healthData}
    <div style="background: #efe; padding: 10px; border: 1px solid green;">
      <strong>Health Data:</strong>
      <pre>{JSON.stringify(healthData, null, 2)}</pre>
    </div>
  {/if}
  
  <h2>Manual Test Links</h2>
  <ul>
    <li><a href="http://localhost:8000/health" target="_blank">Backend Health</a></li>
    <li><a href="http://localhost:8000/api/v1/metrics/system-health" target="_blank">System Health API</a></li>
    <li><a href="http://localhost:8000/docs" target="_blank">API Documentation</a></li>
  </ul>
</div>