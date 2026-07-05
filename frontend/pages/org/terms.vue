<template>
  <div class="max-w-4xl mx-auto py-8 px-4">
    <Head>
      <Title>{{ pageTitle }}</Title>
      <Meta name="description" :content="`Terms for ${establishmentName}`" />
    </Head>

    <div v-if="loading" class="flex justify-center items-center min-h-screen">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100"></div>
    </div>

    <UiAlert v-else-if="error" variant="error" title="Error">
      <p>{{ error }}</p>
      <NuxtLink :to="localePath('/profile')" class="mt-2 inline-block text-sm underline">
        Back to Profile
      </NuxtLink>
    </UiAlert>

    <!-- Generic establishment terms -->
    <div v-else class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-8">
      <div class="text-center mb-8 pb-6 border-b border-neutral-300 dark:border-neutral-600">
        <h1 class="text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-2">
          {{ establishmentName }} - Terms
        </h1>
        <p class="text-sm text-neutral-600 dark:text-neutral-400">
          Terms and Conditions
        </p>
      </div>

      <div class="prose prose-neutral dark:prose-invert max-w-none">
        <p class="text-neutral-700 dark:text-neutral-300">
          Terms for this establishment will be displayed here.
        </p>
      </div>

      <div class="mt-8 text-center">
        <NuxtLink :to="localePath('/profile')" class="inline-block px-6 py-3 bg-neutral-200 dark:bg-neutral-700 hover:bg-neutral-300 dark:hover:bg-neutral-600 text-neutral-900 dark:text-neutral-100 rounded-lg">
          Back to Profile
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()
const establishmentId = route.params.slug as string

const loading = ref(true)
const error = ref('')
const establishmentName = ref('')
const termsUrl = ref('')

const pageTitle = computed(() =>
  establishmentName.value ? `${establishmentName.value} - Terms` : 'Terms'
)

onMounted(async () => {
  try {
    const est = await $fetch(`/api/v1/geo/establishments/${establishmentId}/`)

    if (est.slug === 'parahub-associacao') {
      await router.push(localePath('/org/parahub-associacao/estatutos'))
      return
    }

    establishmentName.value = est.name
    termsUrl.value = est.terms_url

    loading.value = false
  } catch (err) {
    console.error('Failed to load establishment terms:', err)
    error.value = 'Failed to load terms. Please try again later.'
    loading.value = false
  }
})
</script>
