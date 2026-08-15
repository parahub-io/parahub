<template>
  <!-- Standalone host for the scanner; the driver HUD mounts the same component
       as an overlay so an on-shift driver never navigates away from /driver. -->
  <div class="min-h-screen flex flex-col bg-neutral-950">
    <TicketsTicketScanner class="flex-1" @close="navigateTo(localePath('/'))" />
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: 'blank', middleware: 'auth' })

const { t } = useI18n()
const localePath = useLocalePath()

useHead({ title: computed(() => t('tickets.scan_page_title')) })
</script>
