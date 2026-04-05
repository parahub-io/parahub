<template>
  <div class="container mx-auto px-4 py-8 max-w-4xl">
    <div class="prose prose-lg max-w-none">
      <h1 class="text-center mb-2">{{ $t('manifest.title') }}</h1>
      <p class="text-center text-neutral-600 mb-8">
        <em>{{ $t('manifest.subtitle') }}</em>
      </p>

      <div class="space-y-8">
        <section v-for="i in 7" :key="i">
          <h2 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 flex items-center">
            <span class="text-3xl mr-3">{{ i }}.</span> {{ $t(`manifest.principles.${i}.name`) }}
          </h2>
          <p class="text-lg mb-2">{{ $t(`manifest.principles.${i}.statement`) }}</p>
          <div class="pl-8 border-l-4 border-primary/30">
            <p class="text-neutral-700 dark:text-neutral-300">
              <strong>{{ $t(`manifest.principles.${i}.qualifier_label`) }}:</strong> 
              {{ $t(`manifest.principles.${i}.qualifier_text`) }}
            </p>
          </div>
        </section>
      </div>

      <div class="mt-12 p-6 bg-gradient-to-r from-primary/10 to-secondary/10 rounded-lg border border-primary/20">
        <p class="text-center text-lg font-medium">
          {{ $t('manifest.footer') }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({
})
</script>

<style scoped>
.prose h2 {
  @apply mt-8 mb-4;
}
.prose section {
  @apply mb-8;
}
</style>