<template>
  <IoTDeviceSection :title="$t('iot.section_settings')" :help="settingsHelp" :icon="Settings">
    <!-- Name -->
    <form v-if="canManage" @submit.prevent="saveName">
      <label for="device-name" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
        {{ $t('iot.device_name') }}
      </label>
      <div class="flex gap-2">
        <input
          id="device-name" v-model="name" type="text" maxlength="100"
          class="flex-1 min-w-0 px-3 py-2 text-sm rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <UiButton type="submit" variant="secondary" size="sm" :loading="savingName" :disabled="!nameChanged">
          {{ $t('mesh.save') }}
        </UiButton>
      </div>
      <UiAlert v-if="nameError" variant="error" class="mt-2">{{ nameError }}</UiAlert>
    </form>

    <!-- Owner attribution on the public map -->
    <div v-if="isOwner && isMeshRouter" class="mt-4">
      <IoTDeviceToggleRow
        :label="$t('iot.show_owner_label')"
        :description="$t('iot.show_owner_help')"
        :model-value="showOwner"
        :on-text="$t('iot.show_owner_on')"
        :off-text="$t('iot.show_owner_off')"
        :busy="showOwnerBusy"
        :error="showOwnerError"
        @toggle="toggleShowOwner"
      />
    </div>

    <!-- Removal — owner only, and the last thing on the page -->
    <div v-if="isOwner" class="mt-6 pt-4 border-t border-neutral-200 dark:border-neutral-700">
      <div class="font-medium text-sm text-neutral-900 dark:text-neutral-100">{{ $t('iot.confirm_delete_title') }}</div>
      <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1 mb-3">{{ deleteHelp }}</p>
      <UiButton variant="outline-error" size="sm" :icon="Trash2" @click="confirmDelete = true">
        {{ $t('iot.delete') }}
      </UiButton>
    </div>

    <UiConfirmModal
      v-model="confirmDelete"
      :title="$t('iot.confirm_delete_title')"
      :message="$t('iot.confirm_delete_body', { name: device.name })"
      :confirm-label="$t('iot.delete')"
      :cancel-label="$t('iot.cancel')"
      variant="error"
      :icon="Trash2"
      :loading="deleting"
      @confirm="doDelete"
    />
  </IoTDeviceSection>
</template>

<script setup lang="ts">
import { Settings, Trash2 } from 'lucide-vue-next'
import type { IoTDevice } from '~/stores/iot'

interface Props {
  device: IoTDevice
  canManage: boolean
  isOwner: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'deleted'): void }>()

const store = useIoTStore()
const toastStore = useToastStore()
const { t } = useI18n()
const { deviceErrorText } = useIoT()

const isMeshRouter = computed(() => props.device.device_type === 'MESH_ROUTER')

// Only a mesh router can be re-claimed from its sticker MAC after removal, and
// only a mesh router carries the public-map attribution toggle
const deleteHelp = computed(() => (isMeshRouter.value ? t('iot.delete_help') : t('iot.delete_help_generic')))
const settingsHelp = computed(() =>
  isMeshRouter.value ? t('iot.section_settings_help') : t('iot.section_settings_help_generic'))

const name = ref(props.device.name)
const savingName = ref(false)
const nameError = ref<string | null>(null)
const nameChanged = computed(() => {
  const v = name.value.trim()
  return v.length >= 2 && v !== props.device.name
})

// Another surface (a rename elsewhere, a refetch) may move the device under us
watch(() => props.device.name, n => { name.value = n })

const showOwner = computed(() => props.device.show_owner ?? false)
const showOwnerBusy = ref(false)
const showOwnerError = ref<string | null>(null)

const confirmDelete = ref(false)
const deleting = ref(false)

async function saveName() {
  if (savingName.value || !nameChanged.value) return
  savingName.value = true
  nameError.value = null
  try {
    await store.renameDevice(props.device.id, name.value.trim())
  } catch (err: any) {
    nameError.value = deviceErrorText(err)
  } finally {
    savingName.value = false
  }
}

async function toggleShowOwner(next: boolean) {
  if (showOwnerBusy.value) return
  showOwnerBusy.value = true
  showOwnerError.value = null
  try {
    await store.setShowOwner(props.device.id, next)
  } catch (err: any) {
    showOwnerError.value = deviceErrorText(err)
  } finally {
    showOwnerBusy.value = false
  }
}

async function doDelete() {
  if (deleting.value) return
  deleting.value = true
  try {
    await store.deleteDevice(props.device.id)
    toastStore.success(t('iot.delete_success', { name: props.device.name }))
    emit('deleted')
  } catch (err: any) {
    toastStore.error(deviceErrorText(err) || t('iot.delete_failed'))
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}
</script>
