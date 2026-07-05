<template>
  <div v-if="visible" class="fixed inset-0 z-50 overflow-y-auto">
    <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
      <div @click="closeVerifyModal" class="fixed inset-0 bg-neutral-900 bg-opacity-75" aria-hidden="true"></div>

      <div class="relative inline-block w-full max-w-2xl px-4 pt-5 pb-4 overflow-hidden text-left align-bottom transform bg-white dark:bg-neutral-800 rounded-lg shadow-xl sm:my-8 sm:align-middle sm:p-6" role="dialog" aria-modal="true">
        <div class="w-full">
          <h3 class="text-lg font-medium leading-6 text-neutral-900 dark:text-neutral-100 mb-4">
            {{ t('wot.verify_title', { name: profile.display_name || profile.hna }) }}
          </h3>

          <!-- Step 1: Select method -->
          <div v-if="verifyStep === 'select'" class="space-y-4">
            <UiAlert variant="info" :title="t('wot.verify_info_title')">{{ t('wot.verify_info_desc') }}</UiAlert>
            <UiAlert variant="warning" :title="t('wot.verify_warning_title')">{{ t('wot.verify_warning_desc') }}</UiAlert>

            <!-- Verification Method -->
            <div>
              <label for="verify-method" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ t('wot.verification_method') }}
              </label>
              <select
                id="verify-method"
                v-model="selectedMethod"
                class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
              >
                <option value="IN_PERSON">{{ t('wot.method_in_person') }}</option>
                <option value="VIDEO_CALL">{{ t('wot.method_video_call') }}</option>
                <option value="DOCUMENTS">{{ t('wot.method_documents') }}</option>
                <option value="VOUCHED">{{ t('wot.method_vouched') }}</option>
              </select>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                {{ t(`wot.method_${selectedMethod.toLowerCase()}_desc`) }}
              </p>
            </div>

            <div class="flex justify-end gap-3">
              <button
                @click="closeVerifyModal"
                class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                @click="loadVerificationPhoto"
                class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-primary/90"
              >
                {{ t('wot.next_review') }}
              </button>
            </div>
          </div>

          <!-- Step 2: Review verification photo -->
          <div v-if="verifyStep === 'photo'" class="space-y-4">
            <h4 class="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {{ t('wot.photo_review_title') }}
            </h4>
            <p class="text-sm text-neutral-500 dark:text-neutral-400">
              {{ t('wot.photo_review_desc') }}
            </p>

            <!-- Photo display -->
            <div v-if="verificationPhotoUrl" class="flex justify-center">
              <div class="w-48 h-64 rounded-lg overflow-hidden border-2 border-neutral-300 dark:border-neutral-600">
                <img :src="verificationPhotoUrl" alt="Verification photo" class="w-full h-full object-cover" />
              </div>
            </div>
            <div v-else-if="photoLoading" class="flex justify-center py-8">
              <Loader2 class="w-8 h-8 animate-spin text-neutral-400" />
            </div>
            <UiAlert v-else variant="warning">{{ t('wot.no_verification_photo') }}</UiAlert>

            <!-- Confirmation checkbox -->
            <label v-if="verificationPhotoUrl" class="flex items-start gap-3 cursor-pointer">
              <input
                v-model="photoConfirmed"
                type="checkbox"
                class="mt-1 w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
              />
              <span class="text-sm text-neutral-700 dark:text-neutral-300">
                {{ t('wot.photo_confirm_match') }}
              </span>
            </label>

            <div class="flex justify-end gap-3">
              <button
                @click="verifyStep = 'select'"
                class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
              >
                {{ t('common.back') }}
              </button>
              <button
                @click="prepareStatement"
                :disabled="!photoConfirmed"
                class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ t('wot.next_review') }}
              </button>
            </div>
          </div>

          <!-- Step 3: Review and sign statement -->
          <div v-if="verifyStep === 'review'" class="space-y-4">
            <div class="bg-neutral-50 dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-lg p-4">
              <p class="text-sm text-neutral-700 dark:text-neutral-300 mb-2">
                <strong>{{ t('wot.statement_review_title') }}</strong>
              </p>
              <pre class="text-xs font-mono bg-white dark:bg-neutral-800 p-3 rounded border border-neutral-200 dark:border-neutral-700 overflow-x-auto">{{ statementText }}</pre>
            </div>

            <UiAlert variant="warning" :title="t('wot.signature_info_title')">{{ t('wot.signature_info_desc') }}</UiAlert>
            <UiAlert v-if="verifyError" variant="error">{{ verifyError }}</UiAlert>

            <div class="flex justify-end gap-3">
              <button
                @click="verifyStep = 'photo'"
                class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
                :disabled="verifying"
              >
                {{ t('common.back') }}
              </button>
              <button
                @click="signAndVerify"
                :disabled="verifying"
                class="px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-primary/90 flex items-center gap-2"
              >
                <Loader2 v-if="verifying" class="w-4 h-4 animate-spin" />
                {{ verifying ? t('wot.signing') : t('wot.sign_and_verify') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <UiConfirmModal
    v-model="showNoPgpRedirect"
    :title="t('wot.error_no_pgp_key')"
    :message="t('wot.error_no_pgp_key_redirect')"
    :icon="ShieldAlert"
    variant="warning"
    :confirm-label="t('common.continue')"
    @confirm="showNoPgpRedirect = false; navigateTo(localePath('/profile'))"
  />
</template>

<script setup lang="ts">
import { Loader2, ShieldAlert } from 'lucide-vue-next'

const props = defineProps<{ profile: any; modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; 'verified': [] }>()

const { t, te } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()
const toastStore = useToastStore()
const pgp = usePGP()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const verifyStep = ref('select')
const selectedMethod = ref('IN_PERSON')
const statementText = ref('')
const statementData = ref<any>(null)
const verifying = ref(false)
const verifyError = ref('')
const verificationPhotoUrl = ref<string | null>(null)
const photoLoading = ref(false)
const photoConfirmed = ref(false)
const showNoPgpRedirect = ref(false)

const closeVerifyModal = () => {
  visible.value = false
  verifyStep.value = 'select'
  selectedMethod.value = 'IN_PERSON'
  statementText.value = ''
  statementData.value = null
  verifyError.value = ''
  verificationPhotoUrl.value = null
  photoConfirmed.value = false
}

const loadVerificationPhoto = async () => {
  photoLoading.value = true
  verificationPhotoUrl.value = null
  photoConfirmed.value = false

  try {
    await authStore.ensureToken()
    const response = await fetch(`/api/v1/wot/verification-photo/${props.profile.id}/`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })

    if (response.ok) {
      const blob = await response.blob()
      verificationPhotoUrl.value = URL.createObjectURL(blob)
    }
  } catch (error) {
    console.error('Failed to load verification photo:', error)
  } finally {
    photoLoading.value = false
  }

  verifyStep.value = 'photo'
}

const prepareStatement = async () => {
  await pgp.loadKeys()

  if (!pgp.hasKeys.value) {
    verifyError.value = t('wot.error_no_pgp_key')
    showNoPgpRedirect.value = true
    return
  }

  const timestamp = new Date().toISOString()

  statementData.value = {
    action: 'wot_verify',
    verifier_hna: authStore.profile.hna,
    verifier_id: authStore.profile.id,
    verified_hna: props.profile.hna,
    verified_id: props.profile.id,
    method: selectedMethod.value,
    timestamp: timestamp
  }

  statementText.value = JSON.stringify(statementData.value, null, 2)
  verifyStep.value = 'review'
}

const signAndVerify = async () => {
  verifying.value = true
  verifyError.value = ''

  try {
    const signature = await pgp.signMessage(statementText.value)

    await authStore.ensureToken()
    const response = await $fetch('/api/v1/wot/verify/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        verified_user_id: props.profile.id,
        verification_method: selectedMethod.value,
        timestamp: statementData.value.timestamp,
        statement: statementText.value,
        signature: signature
      }
    }) as any

    if (response.success) {
      toastStore.success(t('wot.verify_success', { count: response.new_verification_count }))
      closeVerifyModal()
      emit('verified')
    } else {
      verifyError.value = response.error || t('wot.verify_error_unknown')
    }
  } catch (error: any) {
    console.error('Verification failed:', error)
    // Backend (LocalizedHttpError) sends a machine-readable `code`; localize it.
    // Fall back to the canonical English `detail`, then a generic message.
    const code = error.data?.code
    verifyError.value = (code && te(`wot.error_codes.${code}`))
      ? t(`wot.error_codes.${code}`)
      : (error.data?.detail || error.data?.error || t('wot.verify_error_unknown'))
  } finally {
    verifying.value = false
  }
}
</script>
