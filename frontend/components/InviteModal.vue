<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { X, Copy, Check, RefreshCw } from 'lucide-vue-next'
import QRCode from 'qrcode'

const model = defineModel<boolean>({ required: true })

const authStore = useAuthStore()

const inviteData = ref<any>(null)
const qrCanvas = ref<HTMLCanvasElement | null>(null)
const linkCopied = ref(false)
const showRegenerateConfirm = ref(false)

watch(model, async (isOpen) => {
  if (isOpen) {
    await loadInviteData()
  }
})

async function loadInviteData() {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return
    const response = await $fetch('/api/v1/partners/invite/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    inviteData.value = response
    await nextTick()
    if (qrCanvas.value) {
      await generateQR()
    }
  } catch (error) {
    console.error('Failed to load invite data:', error)
  }
}

async function generateQR() {
  if (!inviteData.value || !qrCanvas.value) return
  try {
    const isDark = document.documentElement.classList.contains('dark')
    await QRCode.toCanvas(qrCanvas.value, inviteData.value.invite_url, {
      width: 256,
      margin: 2,
      color: {
        dark: isDark ? '#FFFFFF' : '#000000',
        light: isDark ? '#374151' : '#FFFFFF',
      },
    })
  } catch (error) {
    console.error('Failed to generate invite QR code:', error)
  }
}

async function toggleActive() {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return
    const response = await $fetch('/api/v1/partners/invite/toggle/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json',
      },
      body: { active: !inviteData.value.is_active },
    })
    inviteData.value = response
  } catch (error) {
    console.error('Failed to toggle invite:', error)
  }
}

async function regenerate() {
  try {
    await authStore.ensureToken()
    if (!authStore.token) return
    const response = await $fetch('/api/v1/partners/invite/regenerate/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    inviteData.value = response
    await nextTick()
    if (qrCanvas.value) {
      await generateQR()
    }
  } catch (error) {
    console.error('Failed to regenerate invite:', error)
  }
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(inviteData.value.invite_url)
    linkCopied.value = true
    setTimeout(() => { linkCopied.value = false }, 2000)
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="model"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]"
      @click.self="model = false"
    >
      <div class="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-300 dark:border-neutral-600 p-6 max-w-md w-full mx-4">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-xl font-bold text-neutral-900 dark:text-neutral-100">
            {{ $t('directory.users.invite_modal.title') }}
          </h3>
          <button
            @click="model = false"
            class="text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
          >
            <X class="w-6 h-6" />
          </button>
        </div>

        <div v-if="inviteData" class="space-y-4">
          <div class="flex justify-center">
            <canvas ref="qrCanvas" role="img" :aria-label="$t('directory.users.invite_modal.qr_aria_label')"></canvas>
          </div>

          <div class="flex items-center justify-between bg-neutral-100 dark:bg-neutral-700/50 rounded-lg px-4 py-3">
            <span class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('directory.users.invite_modal.invited_count_label') }}</span>
            <span class="text-lg font-bold text-neutral-900 dark:text-neutral-100">{{ inviteData.invited_count }}</span>
          </div>

          <div>
            <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              {{ $t('directory.users.invite_modal.invite_link_label') }}
            </label>
            <div class="flex items-center gap-2">
              <input
                :value="inviteData.invite_url"
                readonly
                class="flex-1 px-3 py-2 bg-neutral-50 dark:bg-neutral-700 border border-neutral-300 dark:border-neutral-600 rounded text-sm font-mono"
              />
              <button
                @click="copyLink"
                :class="linkCopied ? 'btn-success btn-icon' : 'btn-ghost btn-icon'"
                :title="linkCopied ? $t('directory.users.invite_modal.copied') : $t('directory.users.invite_modal.copy_button')"
              >
                <Check v-if="linkCopied" class="w-4 h-4" />
                <Copy v-else class="w-4 h-4" />
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between text-sm">
            <span class="text-neutral-600 dark:text-neutral-400">{{ $t('directory.users.invite_modal.status_label') }}</span>
            <span :class="inviteData.is_active ? 'text-success' : 'text-error'">
              {{ inviteData.is_active ? $t('directory.users.invite_modal.active') : $t('directory.users.invite_modal.inactive') }}
            </span>
          </div>

          <div class="flex gap-2 pt-4 border-t border-neutral-200 dark:border-neutral-700">
            <button
              @click="toggleActive"
              class="flex-1"
              :class="inviteData.is_active ? 'btn-primary' : 'btn-success'"
            >
              {{ inviteData.is_active ? $t('directory.users.invite_modal.disable_button') : $t('directory.users.invite_modal.enable_button') }}
            </button>
            <button
              @click="showRegenerateConfirm = true"
              class="flex-1 btn-outline"
            >
              {{ $t('directory.users.invite_modal.regenerate_button') }}
            </button>
          </div>
        </div>

        <div v-else class="text-center py-8">
          <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
        </div>
      </div>
    </div>
  </Teleport>

  <UiConfirmModal
    v-model="showRegenerateConfirm"
    :title="$t('directory.users.invite_modal.regenerate_button')"
    :message="$t('directory.users.invite_modal.regenerate_confirm')"
    :icon="RefreshCw"
    variant="warning"
    :confirm-label="$t('directory.users.invite_modal.regenerate_button')"
    @confirm="regenerate(); showRegenerateConfirm = false"
  />
</template>
