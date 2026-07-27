<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <NuxtLink :to="localePath('/about')" class="inline-flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 mb-4">
      <ArrowLeft class="w-4 h-4" /> {{ $t('about.hero.subtitle', 'About') }}
    </NuxtLink>

    <h1 class="text-2xl sm:text-3xl font-bold text-neutral-900 dark:text-neutral-100 mb-3">{{ $t('data_rights.title') }}</h1>
    <p class="text-neutral-700 dark:text-neutral-300 leading-relaxed mb-2">{{ $t('data_rights.lead') }}</p>
    <p class="text-sm text-neutral-500 dark:text-neutral-400 mb-8">
      <i18n-t keypath="data_rights.full_policy" tag="span" scope="global">
        <template #link>
          <NuxtLink :to="localePath('/about/privacy')" class="text-link">{{ $t('data_rights.full_policy_link') }}</NuxtLink>
        </template>
      </i18n-t>
    </p>

    <div class="space-y-6">
      <!-- 1. Categories -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Database class="w-5 h-5 text-neutral-400" />
          {{ $t('data_rights.categories.title') }}
        </h2>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">{{ $t('data_rights.categories.lead') }}</p>
        <ul class="space-y-3">
          <li v-for="c in categories" :key="c.label" class="text-sm">
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ c.label }}</span>
            <span class="text-neutral-700 dark:text-neutral-300"> — {{ c.detail }}</span>
          </li>
        </ul>

        <div class="mt-5 border-t border-neutral-200 dark:border-neutral-700 pt-4">
          <h3 class="text-sm font-medium text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
            <ShieldOff class="w-4 h-4 text-success" />
            {{ $t('data_rights.categories.not_collected_title') }}
          </h3>
          <ul class="space-y-1.5">
            <li v-for="(n, i) in notCollected" :key="i" class="text-sm text-neutral-700 dark:text-neutral-300 flex gap-2">
              <Check class="w-4 h-4 text-success shrink-0 mt-0.5" />
              <span>{{ n }}</span>
            </li>
          </ul>
        </div>
      </section>

      <!-- 2. Legal basis -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Scale class="w-5 h-5 text-neutral-400" />
          {{ $t('data_rights.basis.title') }}
        </h2>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">{{ $t('data_rights.basis.lead') }}</p>
        <ul class="space-y-3">
          <li v-for="b in basis" :key="b.label" class="text-sm">
            <span class="font-medium text-secondary dark:text-secondary-400">{{ b.label }}</span>
            <span class="text-neutral-700 dark:text-neutral-300"> — {{ b.detail }}</span>
          </li>
        </ul>
      </section>

      <!-- 3. Retention -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Clock class="w-5 h-5 text-neutral-400" />
          {{ $t('data_rights.retention.title') }}
        </h2>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">{{ $t('data_rights.retention.lead') }}</p>
        <ul class="space-y-3">
          <li v-for="r in retention" :key="r.label" class="text-sm">
            <span class="font-medium text-neutral-900 dark:text-neutral-100">{{ r.label }}</span>
            <span class="text-neutral-700 dark:text-neutral-300"> — {{ r.detail }}</span>
          </li>
        </ul>
      </section>

      <!-- 4. How to delete -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2 flex items-center gap-2">
          <Trash2 class="w-5 h-5 text-neutral-400" />
          {{ $t('data_rights.delete.title') }}
        </h2>
        <p class="text-sm text-neutral-600 dark:text-neutral-400 mb-4">{{ $t('data_rights.delete.lead') }}</p>
        <ol class="space-y-2 mb-4">
          <li v-for="(s, i) in deleteSteps" :key="i" class="text-sm text-neutral-700 dark:text-neutral-300 flex gap-3">
            <span class="flex-shrink-0 w-5 h-5 rounded-full bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 text-xs font-semibold flex items-center justify-center">{{ i + 1 }}</span>
            <span>{{ s }}</span>
          </li>
        </ol>

        <UiAlert variant="error" :title="$t('data_rights.delete.effect_title')">
          {{ $t('data_rights.delete.effect') }}
        </UiAlert>

        <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-4">
          <i18n-t keypath="data_rights.delete.alt" tag="span" scope="global">
            <template #email>
              <a href="mailto:info@parahub.io" class="text-link font-mono">info&#64;parahub.io</a>
            </template>
          </i18n-t>
        </p>
      </section>

      <!-- 5. The right to be forgotten × web of trust -->
      <section class="card p-6 border-secondary/40 dark:border-secondary-400/30">
        <h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-3 flex items-center gap-2">
          <Network class="w-5 h-5 text-secondary dark:text-secondary-400" />
          {{ $t('data_rights.forgotten.title') }}
        </h2>
        <p class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed mb-5">{{ $t('data_rights.forgotten.lead') }}</p>

        <div class="space-y-5">
          <div v-for="f in forgotten" :key="f.title" class="flex gap-3">
            <component :is="f.icon" class="w-5 h-5 shrink-0 mt-0.5" :class="f.accent" />
            <div>
              <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ f.title }}</h3>
              <p class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ f.text }}</p>
            </div>
          </div>
        </div>

        <div class="mt-6 border-l-4 border-secondary dark:border-secondary-400 bg-secondary/5 dark:bg-secondary-400/10 rounded-r p-4">
          <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-1">{{ $t('data_rights.forgotten.principle_title') }}</h3>
          <p class="text-sm text-neutral-800 dark:text-neutral-200 leading-relaxed">{{ $t('data_rights.forgotten.principle') }}</p>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, Database, ShieldOff, Check, Scale, Clock, Trash2, Network, UserX, Handshake, FileSignature, KeyRound } from 'lucide-vue-next'

const { t } = useI18n()
const localePath = useLocalePath()

useHead({ title: computed(() => `${t('data_rights.title')} — Parahub`) })
useSeoMeta({
  description: computed(() => t('data_rights.lead')),
  ogTitle: computed(() => `${t('data_rights.title')} — Parahub`),
  ogDescription: computed(() => t('data_rights.lead')),
})

const categories = computed(() => [
  { label: t('data_rights.categories.identity_label'), detail: t('data_rights.categories.identity') },
  { label: t('data_rights.categories.profile_label'), detail: t('data_rights.categories.profile') },
  { label: t('data_rights.categories.pgp_label'), detail: t('data_rights.categories.pgp') },
  { label: t('data_rights.categories.content_label'), detail: t('data_rights.categories.content') },
  { label: t('data_rights.categories.wot_label'), detail: t('data_rights.categories.wot') },
  { label: t('data_rights.categories.agreements_label'), detail: t('data_rights.categories.agreements') },
  { label: t('data_rights.categories.logs_label'), detail: t('data_rights.categories.logs') },
  { label: t('data_rights.categories.matrix_label'), detail: t('data_rights.categories.matrix') },
])

const notCollected = computed(() => [
  t('data_rights.categories.not_collected_1'),
  t('data_rights.categories.not_collected_2'),
  t('data_rights.categories.not_collected_3'),
  t('data_rights.categories.not_collected_4'),
])

const basis = computed(() => [
  { label: t('data_rights.basis.consent_label'), detail: t('data_rights.basis.consent') },
  { label: t('data_rights.basis.contract_label'), detail: t('data_rights.basis.contract') },
  { label: t('data_rights.basis.legitimate_label'), detail: t('data_rights.basis.legitimate') },
  { label: t('data_rights.basis.legal_label'), detail: t('data_rights.basis.legal') },
])

const retention = computed(() => [
  { label: t('data_rights.retention.account_label'), detail: t('data_rights.retention.account') },
  { label: t('data_rights.retention.logs_label'), detail: t('data_rights.retention.logs') },
  { label: t('data_rights.retention.agreements_label'), detail: t('data_rights.retention.agreements') },
  { label: t('data_rights.retention.audit_label'), detail: t('data_rights.retention.audit') },
])

const deleteSteps = computed(() => [
  t('data_rights.delete.step_1'),
  t('data_rights.delete.step_2'),
  t('data_rights.delete.step_3'),
])

const forgotten = computed(() => [
  { icon: UserX, accent: 'text-neutral-400', title: t('data_rights.forgotten.erased_title'), text: t('data_rights.forgotten.erased') },
  { icon: Handshake, accent: 'text-success', title: t('data_rights.forgotten.vouches_title'), text: t('data_rights.forgotten.vouches') },
  { icon: FileSignature, accent: 'text-warning', title: t('data_rights.forgotten.agreements_title'), text: t('data_rights.forgotten.agreements') },
  { icon: KeyRound, accent: 'text-secondary dark:text-secondary-400', title: t('data_rights.forgotten.crypto_title'), text: t('data_rights.forgotten.crypto') },
])
</script>
