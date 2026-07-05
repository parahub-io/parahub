<script setup lang="ts">
// /rental was dissolved into /market/my (2026-06-21): booking requests
// (owner) and my bookings (renter) are now tabs there. This route stays as a
// redirect so old bookmarks and any stragglers still land somewhere useful.
definePageMeta({ middleware: 'auth' })
const localePath = useLocalePath()
await navigateTo(
  localePath({ path: '/market/my', query: { tab: 'requests' } }),
  { redirect: true, replace: true },
)
</script>

<template>
  <div />
</template>
