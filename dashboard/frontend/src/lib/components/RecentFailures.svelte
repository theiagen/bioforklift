<script lang="ts">
  import type { RecentFailure } from '$lib/api';
  
  export let failures: RecentFailure[];
  
  let showAll = false;
  
  $: displayedFailures = showAll ? failures : failures.slice(0, 10);
  
  function formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }
  
  function getTimeDifference(created: string, submitted: string | null): string {
    if (!submitted) return 'N/A';
    
    const createdDate = new Date(created);
    const submittedDate = new Date(submitted);
    const diffMs = submittedDate.getTime() - createdDate.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    
    if (diffMinutes < 60) return `${diffMinutes}m`;
    const hours = Math.floor(diffMinutes / 60);
    const minutes = diffMinutes % 60;
    return `${hours}h ${minutes}m`;
  }
</script>

<div class="card">
  <div class="card-header">
    <h3 class="card-title">Recent Failures</h3>
    <div class="flex items-center space-x-2">
      <span class="text-sm text-gray-600">
        {failures.length} total failures
      </span>
      {#if failures.length > 10}
        <button
          on:click={() => showAll = !showAll}
          class="text-sm text-primary-600 hover:text-primary-700"
        >
          {showAll ? 'Show Less' : 'Show All'}
        </button>
      {/if}
    </div>
  </div>
  
  {#if failures.length === 0}
    <div class="text-center py-8">
      <svg class="mx-auto h-12 w-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
      </svg>
      <h3 class="mt-2 text-sm font-medium text-gray-900">No Recent Failures</h3>
      <p class="mt-1 text-sm text-gray-500">Great job! No failed workflows in recent data.</p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each displayedFailures as failure}
        <div class="border border-red-200 rounded-lg p-4 bg-red-50">
          <div class="flex justify-between items-start">
            <div class="flex-1">
              <div class="flex items-center space-x-2">
                <h4 class="text-sm font-medium text-gray-900">
                  {failure.entity_identifier}
                </h4>
                <span class="status-badge status-error">
                  {failure.workflow_state}
                </span>
              </div>
              
              <div class="mt-1 text-sm text-gray-600">
                <span class="font-medium">Config:</span> 
                {failure.config_name || failure.config_id || 'Unknown'}
              </div>
              
              <div class="mt-2 grid grid-cols-2 gap-4 text-xs text-gray-500">
                <div>
                  <span class="font-medium">Created:</span>
                  {formatDate(failure.created_at)}
                </div>
                <div>
                  <span class="font-medium">Processing Time:</span>
                  {getTimeDifference(failure.created_at, failure.submitted_at)}
                </div>
              </div>
              
              {#if failure.terra_submission_id}
                <div class="mt-2 text-xs text-gray-500">
                  <span class="font-medium">Submission ID:</span>
                  <code class="bg-gray-100 px-1 rounded">{failure.terra_submission_id}</code>
                </div>
              {/if}
              
              {#if failure.terra_workflow_id}
                <div class="mt-1 text-xs text-gray-500">
                  <span class="font-medium">Workflow ID:</span>
                  <code class="bg-gray-100 px-1 rounded">{failure.terra_workflow_id}</code>
                </div>
              {/if}
            </div>
            
            <div class="flex-shrink-0 ml-4">
              <svg class="h-5 w-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.728-.833-2.498 0L4.316 15.5c-.77.833.192 2.5 1.732 2.5z"></path>
              </svg>
            </div>
          </div>
        </div>
      {/each}
    </div>
    
    {#if failures.length > 10 && !showAll}
      <div class="text-center mt-4">
        <button
          on:click={() => showAll = true}
          class="text-sm text-primary-600 hover:text-primary-700"
        >
          Show {failures.length - 10} more failures
        </button>
      </div>
    {/if}
  {/if}
</div>