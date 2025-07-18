<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  export let error: string;
  
  const dispatch = createEventDispatcher();
  
  function handleRetry() {
    dispatch('retry');
  }
</script>

<div class="card bg-red-50 border-red-200">
  <div class="flex items-center space-x-3">
    <div class="flex-shrink-0">
      <svg class="h-8 w-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.728-.833-2.498 0L4.316 15.5c-.77.833.192 2.5 1.732 2.5z"></path>
      </svg>
    </div>
    <div class="flex-1">
      <h3 class="text-lg font-medium text-red-800">Error Loading Data</h3>
      <p class="text-red-700 mt-1">{error}</p>
    </div>
    <div class="flex-shrink-0">
      <button
        on:click={handleRetry}
        class="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 transition-colors"
      >
        Try Again
      </button>
    </div>
  </div>
</div>