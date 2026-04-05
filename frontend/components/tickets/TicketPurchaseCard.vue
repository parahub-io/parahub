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
            {{ $t('tickets.price', { sats: tt.price_sats.toLocaleString() }) }}
          </span>
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
        :disabled="!!buyingId"
        @click="$emit('buy', tt)"
      >
        <Zap class="w-3.5 h-3.5 mr-1" />
        {{ $t('tickets.buy') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Zap } from 'lucide-vue-next'

interface TicketType {
  id: string
  name: string
  description: string
  price_sats: number
  max_capacity: number | null
  sold_count: number
  is_sold_out: boolean
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
</script>
