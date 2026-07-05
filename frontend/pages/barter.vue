<template>
  <div />
</template>

<script setup lang="ts">
// Barter moved into /market/my as the "Barter" tab (personal, auth-scoped — same
// audience as "My market"). Keep this URL alive as a permanent redirect so existing
// links (the market barter banner, the landing "Start bartering" CTA, deep links,
// indexed pages) don't 404.
const localePath = useLocalePath()
await navigateTo(
  localePath({ path: '/market/my', query: { tab: 'barter' } }),
  { redirectCode: 301, replace: true },
)
</script>
