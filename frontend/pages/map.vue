<template>
  <div>
    <h1 class="sr-only">{{ $t('nav.map', 'Map') }}</h1>
    <MapView />
  </div>
</template>

<script setup>
definePageMeta({
  order: 2,
  keepalive: true
})

// Track onboarding: user has explored the map
if (import.meta.client) {
  localStorage.setItem('onboarding:map', '1')
}
</script>
