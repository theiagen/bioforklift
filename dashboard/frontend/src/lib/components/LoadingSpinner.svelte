<script lang="ts">
  export let size: 'sm' | 'md' | 'lg' = 'md';
  export let color: string = 'primary-600';
  
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8', 
    lg: 'h-12 w-12'
  };
</script>

<div class="flex justify-center items-center">
  <div class="loading-spinner {sizeClasses[size]} border-{color}"></div>
</div>