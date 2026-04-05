<template>
  <div class="bg-white dark:bg-neutral-800 rounded-lg overflow-hidden animate-pulse">
    <!-- Image skeleton -->
    <div class="w-full aspect-video bg-neutral-300 dark:bg-neutral-700"></div>

    <!-- Content skeleton -->
    <div class="px-4 pt-4 pb-2">
      <!-- Badge -->
      <div class="flex justify-between items-start mb-2">
        <div class="h-5 w-16 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
        <div class="h-4 w-24 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
      </div>

      <!-- Title -->
      <div class="h-5 bg-neutral-300 dark:bg-neutral-700 rounded mb-2 w-3/4"></div>

      <!-- Description -->
      <div class="space-y-2 mb-3">
        <div class="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-full"></div>
        <div class="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-5/6"></div>
      </div>

      <!-- Price -->
      <div class="h-6 bg-neutral-300 dark:bg-neutral-700 rounded w-28 mb-3"></div>

      <!-- Owner info -->
      <div class="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700 flex items-center justify-between">
        <div class="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-20"></div>
        <div class="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-16"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
// No props needed - pure presentational component
</script>

<style scoped>
@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>
