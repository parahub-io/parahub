<template>
  <EstablishmentDetail :id="route.params.slug" />
</template>

<script setup>
const route = useRoute()
</script>
