<script setup lang="ts">
// Profile URLs permanently moved from /u/<name> to /@<name>. This catch-all
// keeps every old link working forever: chats, printed QR badges, stored
// notification URLs. Handles both SSR hits (real HTTP 301) and client-side
// router navigation (old URLs persisted in the notifications table).
const route = useRoute()
const src = route.fullPath
await navigateTo(src.includes('/u/') ? src.replace('/u/', '/@') : '/', {
  redirectCode: 301,
  replace: true,
})
</script>

<template>
  <div />
</template>
