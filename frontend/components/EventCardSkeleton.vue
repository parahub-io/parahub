<template>
  <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden animate-pulse">
    <!-- Cover image -->
    <div class="h-36 bg-neutral-300 dark:bg-neutral-700"></div>

    <!-- Content -->
    <div class="p-4 space-y-2.5">
      <!-- Category + Type badge -->
      <div class="flex items-center justify-between gap-2">
        <div class="h-4 w-20 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
        <div class="h-5 w-14 bg-neutral-300 dark:bg-neutral-700 rounded-full"></div>
      </div>

      <!-- Title -->
      <div class="h-5 bg-neutral-300 dark:bg-neutral-700 rounded w-3/4"></div>

      <!-- Date -->
      <div class="flex items-center gap-2">
        <div class="h-4 w-4 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
        <div class="h-4 w-36 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
      </div>

      <!-- Location -->
      <div class="flex items-center gap-2">
        <div class="h-4 w-4 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
        <div class="h-4 w-28 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between pt-2.5 border-t border-neutral-100 dark:border-neutral-700">
        <div class="flex items-center gap-1.5">
          <div class="w-5 h-5 bg-neutral-300 dark:bg-neutral-700 rounded-full"></div>
          <div class="h-3 w-16 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="h-3 w-3 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
          <div class="h-3 w-8 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
</script>
