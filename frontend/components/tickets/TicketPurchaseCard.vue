<template>
  <div v-if="ticketTypes.length" class="space-y-3">
    <div
      v-for="tt in ticketTypes"
      :key="tt.id"
      class="border border-neutral-200 dark:border-neutral-700 rounded-xl p-4 flex items-center gap-4"
    >
      <div class="flex-1 min-w-0">
        <div class="font-medium text-neutral-900 dark:text-white">{{ tt.name }}</div>
        <div v-if="tt.description" class="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
          {{ tt.description }}
        </div>
        <div class="flex items-center gap-3 mt-1.5 text-xs text-neutral-400">
          <span class="font-semibold text-secondary dark:text-secondary-400">
            <template v-if="tt.price_eur != null">
              {{ $t('tickets.price_eur', { eur: formatEur(tt.price_eur) }) }}
              <span v-if="tt.price_sats != null" class="font-normal text-neutral-400">
                · {{ $t('tickets.approx_sats', { sats: tt.price_sats.toLocaleString() }) }}
              </span>
            </template>
            <template v-else-if="tt.price_sats != null">
              {{ $t('tickets.price', { sats: tt.price_sats.toLocaleString() }) }}
            </template>
            <template v-else>{{ $t('tickets.price_unavailable') }}</template>
          </span>
          <span v-if="tt.validity_minutes" class="inline-flex items-center gap-1">
            <Clock class="w-3 h-3" />
            {{ formatValidity(tt.validity_minutes) }}
          </span>
          <UiBadge v-if="tt.agency_id" variant="secondary" type="soft" size="sm">
            {{ $t('tickets.network_wide') }}
          </UiBadge>
          <UiBadge v-if="tt.concession_category" variant="warning" type="soft" size="sm">
            {{ $t(`tickets.concession_${tt.concession_category.toLowerCase()}`) }}
          </UiBadge>
          <span v-if="tt.max_capacity">
            {{ $t('tickets.capacity', { sold: tt.sold_count, max: tt.max_capacity }) }}
          </span>
        </div>
      </div>

      <UiBadge v-if="tt.is_sold_out" variant="error" type="soft">
        {{ $t('tickets.sold_out') }}
      </UiBadge>
      <UiButton
        v-else
        variant="primary"
        size="sm"
        :loading="buyingId === tt.id"
        :disabled="!!buyingId || tt.price_sats == null"
        @click="$emit('buy', tt)"
      >
        <Zap class="w-3.5 h-3.5 mr-1" />
        {{ $t('tickets.buy') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Clock, Zap } from 'lucide-vue-next'

interface TicketType {
  id: string
  name: string
  description: string
  price_sats: number | null
  price_eur?: number | null
  max_capacity: number | null
  sold_count: number
  is_sold_out: boolean
  validity_minutes?: number | null
  agency_id?: string | null
  concession_category?: string
  operator_ln_address: string
  operator_spark_address: string
}

defineProps<{
  ticketTypes: TicketType[]
  buyingId?: string | null
}>()

defineEmits<{
  (e: 'buy', tt: TicketType): void
}>()

const { t } = useI18n()

function formatEur(v: number) {
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatValidity(minutes: number) {
  if (minutes % 1440 === 0) return t('tickets.validity_days', { n: minutes / 1440 })
  if (minutes % 60 === 0) return t('tickets.validity_hours', { n: minutes / 60 })
  return t('tickets.validity_min', { n: minutes })
}
</script>
