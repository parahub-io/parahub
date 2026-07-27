<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <PageHeader
      :title="$t('tips.title')"
      :subtitle="$t('tips.subtitle')"
      :create-to="localePath('/tips/new')"
      :create-label="$t('tips.create')"
    />

    <div v-if="!batches.length" class="py-12 text-center">
      <Banknote class="w-12 h-12 mx-auto text-neutral-400" />
      <h3 class="mt-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {{ $t('tips.empty.title') }}
      </h3>
      <p class="mt-2 text-sm text-neutral-500 dark:text-neutral-400 max-w-md mx-auto">
        {{ $t('tips.empty.text') }}
      </p>
      <UiButton class="mt-6" :to="localePath('/tips/new')" :icon="Plus">
        {{ $t('tips.create') }}
      </UiButton>
    </div>

    <div v-else class="border border-neutral-300 dark:border-neutral-600 rounded-lg overflow-hidden divide-y divide-neutral-300 dark:divide-neutral-600">
      <NuxtLink
        v-for="batch in batches"
        :key="batch.id"
        :to="localePath(`/tips/${batch.id}`)"
        class="flex items-center gap-4 p-4 hover:bg-primary-100 dark:hover:bg-primary-900/40"
      >
        <Banknote class="w-5 h-5 text-neutral-400 shrink-0" />
        <div class="min-w-0 flex-1">
          <div class="font-semibold text-neutral-900 dark:text-neutral-100">
            {{ $t("tips.batch.notes", { count: batch.notes.length }, batch.notes.length) }} ·
            {{ formatSats(batch.sats) }}
          </div>
          <div class="text-sm text-neutral-500 dark:text-neutral-400 truncate">
            {{ batch.message || $t('tips.batch.noMessage') }}
          </div>
        </div>
        <div class="text-xs text-neutral-500 dark:text-neutral-400 shrink-0 text-right">
          {{ new Date(batch.createdAt).toLocaleDateString() }}
        </div>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Banknote, Plus } from 'lucide-vue-next'

definePageMeta({ middleware: 'auth' })

const localePath = useLocalePath()
const { t } = useI18n()
const { batches, load } = useTipBatches()

const formatSats = (sats: number) => `${sats.toLocaleString()} sats`

onMounted(load)

useHead({ title: t('tips.title') })
</script>
