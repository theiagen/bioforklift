<!--
  Authentication wrapper component that handles login state and protects routes
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { authStatus, authLoading, user, initAuth } from '$lib/stores/auth';
  import LoadingSpinner from './LoadingSpinner.svelte';
  
  let mounted = false;
  
  onMount(async () => {
    await initAuth();
    mounted = true;
  });
  
  // Reactive statements for debugging
  $: if (mounted) {
    console.log('Auth Status:', $authStatus);
    console.log('User:', $user);
  }
</script>

{#if !mounted || $authLoading}
  <!-- Loading state while checking authentication -->
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="text-center">
      <div class="mb-4">
        <div class="text-4xl mb-2">🧬</div>
        <h1 class="text-2xl font-bold text-gray-900">Bioforklift Dashboard</h1>
        <p class="text-gray-600 mt-2">Checking authentication...</p>
      </div>
      <LoadingSpinner />
    </div>
  </div>
{:else if !$authStatus.authenticated}
  <!-- Not authenticated - show login prompt -->
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600">
    <div class="max-w-md w-full mx-4">
      <div class="bg-white rounded-lg shadow-xl p-8 text-center">
        <div class="text-5xl mb-4">🧬</div>
        <h1 class="text-3xl font-bold text-gray-900 mb-2">Bioforklift Dashboard</h1>
        <p class="text-gray-600 mb-6">Monitor your bioinformatics workflows and pipeline performance</p>
        
        <div class="bg-gray-50 rounded-lg p-4 mb-6 text-left">
          <h3 class="font-semibold text-gray-900 mb-2">Dashboard Features:</h3>
          <ul class="text-sm text-gray-600 space-y-1">
            <li>• Daily workflow run summaries</li>
            <li>• Real-time processing status</li>
            <li>• Configuration metrics and trends</li>
            <li>• Error tracking and debugging</li>
            <li>• System health monitoring</li>
          </ul>
        </div>
        
        <a 
          href="/auth/login"
          class="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-blue-700 transition-colors inline-block"
        >
          🔐 Sign in with Google
        </a>
        
        <p class="text-sm text-gray-500 mt-4">
          Secure access with Google Cloud Platform authentication
        </p>
      </div>
    </div>
  </div>
{:else}
  <!-- Authenticated - show app content -->
  <div class="min-h-screen bg-gray-50">
    <!-- Header with user info -->
    <header class="bg-white shadow-sm border-b border-gray-200">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between items-center h-16">
          <div class="flex items-center">
            <span class="text-2xl mr-3">🧬</span>
            <h1 class="text-xl font-semibold text-gray-900">Bioforklift Dashboard</h1>
            {#if $authStatus.project}
              <div class="ml-4 text-sm text-gray-500">
                <span class="font-medium">Project:</span> {$authStatus.project.project_id}
                <span class="mx-2">•</span>
                <span class="font-medium">Dataset:</span> {$authStatus.project.dataset_id}
              </div>
            {/if}
          </div>
          
          <div class="flex items-center space-x-4">
            {#if $user}
              <div class="flex items-center space-x-3">
                {#if $user.picture}
                  <img 
                    src={$user.picture} 
                    alt="Profile" 
                    class="w-8 h-8 rounded-full"
                  />
                {/if}
                <span class="text-sm font-medium text-gray-700">
                  {$user.name || $user.email}
                </span>
                <a 
                  href="/auth/logout"
                  class="text-sm text-gray-500 hover:text-gray-700 px-3 py-1 rounded hover:bg-gray-100"
                >
                  Sign Out
                </a>
              </div>
            {/if}
          </div>
        </div>
      </div>
    </header>
    
    <!-- Main content -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <slot />
    </main>
  </div>
{/if}