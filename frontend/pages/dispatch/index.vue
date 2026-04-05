<template>
  <div />
</template>

<script setup lang="ts">
const localePath = useLocalePath()
navigateTo(localePath('/dispatch/assignments'), { replace: true })
</script>
