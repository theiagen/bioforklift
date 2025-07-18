<script lang="ts">
  import '../app.css';
  import AuthWrapper from '$lib/components/AuthWrapper.svelte';
</script>

<AuthWrapper>
  <slot />
</AuthWrapper>