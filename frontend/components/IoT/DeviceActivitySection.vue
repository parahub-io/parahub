<template>
  <IoTDeviceSection :title="$t('iot.activity_title')" :help="$t('iot.section_activity_help')" :icon="ScrollText">
    <div v-if="loading" class="py-8 text-center text-neutral-500 dark:text-neutral-400" role="status">
      <Loader2 class="w-6 h-6 animate-spin mx-auto" aria-hidden="true" />
      <span class="sr-only">{{ $t('iot.loading') }}</span>
    </div>

    <UiAlert v-else-if="error" variant="error">{{ error }}</UiAlert>

    <p v-else-if="!entries.length" class="text-sm text-neutral-500 dark:text-neutral-400 py-4 text-center">
      {{ $t('iot.activity_empty') }}
    </p>

    <ol
      v-else
      class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700"
    >
      <li v-for="entry in entries" :key="entry.id" class="px-3 py-2 text-sm">
        <div class="flex items-center justify-between gap-2">
          <div class="min-w-0 flex-1">
            <span class="text-neutral-900 dark:text-neutral-100">{{ actionLabel(entry) }}</span>
            <span
              v-if="entry.status === 403"
              class="ml-1.5 text-xs text-error"
            >{{ $t('iot.activity_denied') }}</span>
          </div>
          <span
            class="text-xs text-neutral-500 dark:text-neutral-400 shrink-0"
            :title="formatDate(entry.created_at)"
          >{{ formatRelativeTime(entry.created_at) }}</span>
        </div>
        <div class="flex items-center gap-1.5 mt-0.5 min-w-0">
          <span class="text-xs text-neutral-500 dark:text-neutral-400 truncate">
            {{ entry.actor_name || $t('iot.activity_actor_gone') }}
            <span v-if="entry.actor_hna" class="ml-1">{{ entry.actor_hna }}</span>
          </span>
          <UiBadge v-if="entry.role" :variant="roleVariant(entry.role)" type="soft" size="sm">
            {{ roleLabel(entry.role) }}
          </UiBadge>
        </div>
      </li>
    </ol>

    <p v-if="entries.length" class="text-xs text-neutral-500 dark:text-neutral-400 mt-3">
      {{ $t('iot.activity_footnote') }}
    </p>
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Loader2, ScrollText } from 'lucide-vue-next'
import type { DeviceActionEntry } from '~/stores/iot'

interface Props {
  deviceId: string
}

const props = defineProps<Props>()

const store = useIoTStore()
const { t } = useI18n()
const { formatDate, formatRelativeTime } = useIoT()

const loading = ref(true)
const error = ref<string | null>(null)
const entries = ref<DeviceActionEntry[]>([])

onMounted(async () => {
  try {
    entries.value = await store.getDeviceActivity(props.deviceId)
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || t('iot.activity_failed')
  } finally {
    loading.value = false
  }
})

// Slugs come from the endpoint path, so an action shipped after this build
// still reads as something rather than nothing.
function actionLabel(entry: DeviceActionEntry): string {
  const [slug, suffix] = entry.action.split(':')
  // The device root carries no verb of its own — only DELETE reaches the journal
  if (slug === 'device' && entry.method === 'DELETE') return t('iot.action.device_deleted')
  const base = t(`iot.action.${slug}`, slug)
  return suffix === 'read' ? t('iot.activity_disclosed', { what: base }) : base
}

function roleLabel(role: string): string {
  if (role === 'OWNER') return t('iot.role_owner')
  if (role === 'MANAGER') return t('iot.role_manager')
  return t('iot.role_viewer')
}

function roleVariant(role: string): 'neutral' | 'secondary' {
  return role === 'MANAGER' ? 'secondary' : 'neutral'
}
</script>
