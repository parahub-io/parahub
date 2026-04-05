<template>
  <UiBadge v-if="isStaff && isDemo" variant="warning" type="outline" size="sm">
    Demo
  </UiBadge>
</template>

<script setup>
const props = defineProps({
  isDemo: { type: Boolean, default: false }
})

const authStore = useAuthStore()
const isStaff = computed(() => authStore.user?.is_staff ?? false)
</script>
