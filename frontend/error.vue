<template>
  <div class="min-h-screen bg-neutral-50 dark:bg-neutral-900 flex items-center justify-center px-4">
    <div class="text-center max-w-md">
      <img
        v-if="is404"
        src="/images/para/puzzled.png"
        alt="Para"
        class="mx-auto h-48 w-auto mb-6"
      >
      <img
        v-else
        src="/images/para/alert.png"
        alt="Para"
        class="mx-auto h-48 w-auto mb-6"
      >

      <h1 class="text-6xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
        {{ error?.statusCode || 500 }}
      </h1>
      <p class="text-lg text-neutral-600 dark:text-neutral-400 mb-8">
        {{ message }}
      </p>

      <button class="btn-primary" @click="handleError">
        {{ $t('go_home', 'Go back home') }}
      </button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  error: Object
})

const { t } = useI18n()
const localePath = useLocalePath()

const is404 = computed(() => props.error?.statusCode === 404)

const message = computed(() => {
  if (is404.value) {
    return t('error_not_found', 'Page not found')
  }
  return t('error_server', 'Something went wrong')
})

const handleError = () => clearError({ redirect: localePath('/') })
</script>
