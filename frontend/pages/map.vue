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
</script>
