<template>
  <!-- Calm placeholder matching the recon card footprint (viewport + readout rows +
       footer band) so the loading→content swap is an in-place reveal, no layout jump. -->
  <div class="rounded-lg overflow-hidden bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 animate-pulse">
    <!-- Sensor viewport -->
    <div class="m-2 rounded-md aspect-[5/4] bg-neutral-200 dark:bg-neutral-800" />

    <!-- Readouts -->
    <div class="px-3 pb-2.5">
      <!-- Place headline -->
      <div class="mb-1.5 flex items-center gap-1.5">
        <div class="w-3.5 h-3.5 rounded-sm bg-neutral-200 dark:bg-neutral-800" />
        <div class="h-4 w-2/3 rounded bg-neutral-200 dark:bg-neutral-800" />
      </div>

      <div class="h-px bg-neutral-200 dark:bg-neutral-800" />

      <!-- Readout lines -->
      <div class="py-2 space-y-2">
        <div class="h-3 w-full rounded bg-neutral-200 dark:bg-neutral-800" />
        <div class="h-3 w-5/6 rounded bg-neutral-200 dark:bg-neutral-800" />
        <div class="h-3 w-3/4 rounded bg-neutral-200 dark:bg-neutral-800" />
        <div class="h-3 w-1/2 rounded bg-neutral-200 dark:bg-neutral-800" />
      </div>

      <div class="h-px bg-neutral-200 dark:bg-neutral-800" />

      <!-- Footer band -->
      <div class="mt-2 h-8 rounded-md bg-neutral-200 dark:bg-neutral-800" />
    </div>
  </div>
</template>

<script setup lang="ts">
// Pure presentational skeleton — no props.
</script>
