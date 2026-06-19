<template>
  <div class="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800">
    <!-- Desktop layout -->
    <div class="hidden md:block">
      <!-- Main info row -->
      <div class="flex items-start gap-6 p-8 pb-6">
        <!-- Avatar + Info -->
        <div class="flex items-center gap-4 flex-1">
          <div
            @click="showAvatarModal = true"
            class="w-20 h-20 rounded-2xl flex-shrink-0 shadow-md overflow-hidden cursor-pointer group relative"
          >
            <img
              v-if="avatarUrl"
              :src="avatarUrl"
              :alt="userInitials"
              class="w-full h-full object-cover"
            />
            <div v-else class="w-full h-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
              <span class="text-3xl font-bold text-black">{{ userInitials }}</span>
            </div>
            <!-- Hover overlay -->
            <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
              <Camera class="w-6 h-6 text-white" />
            </div>
          </div>

          <div class="flex-1 min-w-0">
            <h1 v-if="displayName" class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50 mb-1">
              {{ displayName }}
            </h1>
            <p class="text-base text-neutral-500 dark:text-neutral-400 mb-2">{{ userHNA || user?.profile?.hna || user?.email }}</p>

            <input
              id="profile-bio"
              v-model="bioText"
              type="text"
              maxlength="300"
              :aria-label="$t('profile.bio_placeholder')"
              :placeholder="$t('profile.bio_placeholder')"
              class="w-full text-sm px-0 py-1 bg-transparent border-0 border-b border-transparent hover:border-neutral-300 dark:hover:border-neutral-600 focus:border-primary focus:ring-0 text-neutral-700 dark:text-neutral-300 placeholder-neutral-400 transition-colors"
              @blur="saveBio"
              @keydown.enter="($event.target as HTMLInputElement).blur()"
            />
          </div>
        </div>

      </div>

      <!-- Preferences section -->
      <div class="border-t border-neutral-200 dark:border-neutral-800 px-8 py-5">
        <div class="flex items-center gap-4">
          <select
            id="profile-language"
            v-model="selectedLanguage"
            class="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 hover:border-neutral-400 dark:hover:border-neutral-600 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all cursor-pointer"
            :aria-label="$t('profile.preferences.language_label')"
          >
            <option value="en">English</option>
            <option value="ru">Русский</option>
            <option value="pt">Português</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
          </select>
          <select
            id="profile-currency"
            v-model="selectedCurrency"
            @change="updateCurrency"
            class="flex-1 px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 hover:border-neutral-400 dark:hover:border-neutral-600 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all cursor-pointer"
            :aria-label="$t('profile.preferences.currency_label')"
          >
            <option v-for="currency in availableCurrencies" :key="currency" :value="currency">
              {{ currency }}
            </option>
          </select>
          <div class="relative flex-1">
            <select
              id="profile-country"
              v-model="selectedCountry"
              @change="saveCountry"
              class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 hover:border-neutral-400 dark:hover:border-neutral-600 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all cursor-pointer"
              :aria-label="$t('profile.preferences.country_label')"
            >
              <option value="">{{ $t('profile.preferences.country_not_set') }}</option>
              <option v-for="c in COUNTRIES" :key="c.code" :value="c.code">
                {{ c.flag }} {{ c.name }}
              </option>
            </select>
            <span v-if="countrySaving" class="absolute right-8 top-1/2 -translate-y-1/2 text-sm text-neutral-400">...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Mobile layout -->
    <div class="md:hidden p-6">
      <div class="space-y-4">
        <!-- Avatar -->
        <div class="flex justify-center">
          <div
            @click="showAvatarModal = true"
            class="w-24 h-24 rounded-2xl flex-shrink-0 overflow-hidden cursor-pointer group relative"
          >
            <img
              v-if="avatarUrl"
              :src="avatarUrl"
              :alt="userInitials"
              class="w-full h-full object-cover"
            />
            <div v-else class="w-full h-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
              <span class="text-4xl font-bold text-black">{{ userInitials }}</span>
            </div>
            <!-- Hover overlay -->
            <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
              <Camera class="w-8 h-8 text-white" />
            </div>
          </div>
        </div>

        <!-- Name & HNA -->
        <div class="space-y-1 text-center">
          <h1 v-if="displayName" class="text-2xl font-semibold text-neutral-900 dark:text-neutral-50">
            {{ displayName }}
          </h1>
          <p class="text-base text-neutral-500 dark:text-neutral-400">{{ userHNA || user?.profile?.hna || user?.email }}</p>
        </div>

        <input
          id="profile-bio-mobile"
          v-model="bioText"
          type="text"
          maxlength="300"
          :aria-label="$t('profile.bio_placeholder')"
          :placeholder="$t('profile.bio_placeholder')"
          class="w-full text-sm text-center px-2 py-1 bg-transparent border-0 border-b border-transparent hover:border-neutral-300 dark:hover:border-neutral-600 focus:border-primary focus:ring-0 text-neutral-700 dark:text-neutral-300 placeholder-neutral-400 transition-colors"
          @blur="saveBio"
          @keydown.enter="($event.target as HTMLInputElement).blur()"
        />

        <!-- Preferences (full width) -->
        <div class="w-full space-y-2 pt-2 border-t border-neutral-200 dark:border-neutral-800">
          <select
            id="profile-language-mobile"
            v-model="selectedLanguage"
            class="w-full px-3 py-2.5 text-base border border-neutral-300 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :aria-label="$t('profile.preferences.language_label')"
          >
            <option value="en">English</option>
            <option value="ru">Русский</option>
            <option value="pt">Português</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
          </select>
          <select
            id="profile-currency-mobile"
            v-model="selectedCurrency"
            @change="updateCurrency"
            class="w-full px-3 py-2.5 text-base border border-neutral-300 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            :aria-label="$t('profile.preferences.currency_label')"
          >
            <option v-for="currency in availableCurrencies" :key="currency" :value="currency">
              {{ currency }}
            </option>
          </select>
          <div class="relative">
            <select
              id="profile-country-mobile"
              v-model="selectedCountry"
              @change="saveCountry"
              class="w-full px-3 py-2.5 text-base border border-neutral-300 dark:border-neutral-700 rounded-lg bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              :aria-label="$t('profile.preferences.country_label')"
            >
              <option value="">{{ $t('profile.preferences.country_not_set') }}</option>
              <option v-for="c in COUNTRIES" :key="c.code" :value="c.code">
                {{ c.flag }} {{ c.name }}
              </option>
            </select>
            <span v-if="countrySaving" class="absolute right-8 top-1/2 -translate-y-1/2 text-sm text-neutral-400">...</span>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <!-- Avatar Edit Modal -->
      <div
        v-if="showAvatarModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
        @click="showAvatarModal = false"
      >
        <div
          class="bg-white dark:bg-neutral-900 rounded-2xl p-6 max-w-sm w-full space-y-4"
          @click.stop
        >
          <h3 class="text-xl font-semibold text-neutral-900 dark:text-neutral-50 text-center">
            {{ $t('profile.photos.avatar_label', 'Avatar') }}
          </h3>

          <!-- Current Avatar Preview -->
          <div class="flex justify-center">
            <div class="w-32 h-32 rounded-2xl overflow-hidden border-2 border-neutral-200 dark:border-neutral-700">
              <img
                v-if="avatarUrl"
                :src="avatarUrl"
                alt="Avatar"
                class="w-full h-full object-cover"
              />
              <div v-else class="w-full h-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
                <span class="text-5xl font-bold text-black">{{ userInitials }}</span>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="space-y-2">
            <label class="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary hover:bg-primary/90 rounded-lg text-black font-medium transition-colors cursor-pointer">
              <Upload v-if="!avatarUploading" class="w-5 h-5" />
              <Loader2 v-else class="w-5 h-5 animate-spin" />
              {{ avatarUploading ? $t('profile.photos.uploading', 'Uploading...') : $t('profile.photos.upload', 'Upload photo') }}
              <input
                type="file"
                accept="image/*"
                class="hidden"
                @change="uploadAvatar"
                :disabled="avatarUploading"
              />
            </label>

            <button
              v-if="avatarUrl"
              @click="deleteAvatar"
              :disabled="avatarDeleting"
              class="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 rounded-lg text-red-700 dark:text-red-400 font-medium transition-colors"
            >
              <Trash2 v-if="!avatarDeleting" class="w-5 h-5" />
              <Loader2 v-else class="w-5 h-5 animate-spin" />
              {{ avatarDeleting ? '...' : $t('profile.photos.delete', 'Delete') }}
            </button>

            <button
              @click="showAvatarModal = false"
              class="w-full px-4 py-2 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg text-neutral-700 dark:text-neutral-300 font-medium transition-colors"
            >
              {{ $t('common.close', 'Close') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Upload, Loader2, Trash2, Camera } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import { useNotification } from '~/composables/useNotification'

const props = defineProps<{
  userHNA: string
}>()

const { t, locale } = useI18n()
const authStore = useAuthStore()
const { showSuccess, showError } = useNotification()

const user = computed(() => authStore.user)

// display_name is present in both SSR session data and /me/ response;
// first_name/last_name only exist after fetchUser() — relying on them caused
// the name to pop in post-mount and shift the whole page down
const displayName = computed(() => {
  const u = user.value
  if (!u) return ''
  return u.profile?.display_name || `${u.first_name || ''} ${u.last_name || ''}`.trim()
})

const userInitials = computed(() => {
  const parts = displayName.value.split(' ').filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return user.value?.email?.[0]?.toUpperCase() || '?'
})

const avatarUrl = computed(() => user.value?.profile?.avatar_url || null)

// Bio
const bioText = ref(authStore.profile?.bio || '')
// Store profile is repopulated after mount (fetchUser, profile switch) —
// sync the field unless the user already edited it
watch(() => authStore.profile?.bio, (val, oldVal) => {
  if (typeof val === 'string' && bioText.value === (oldVal || '')) bioText.value = val
})
const saveBio = async () => {
  const trimmed = bioText.value.trim()
  if (trimmed === (authStore.profile?.bio || '')) return
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/', {
      method: 'PUT',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { bio: trimmed },
    })
    if (authStore.profile) (authStore.profile as any).bio = trimmed
  } catch { /* silent */ }
}

// Avatar modal state
const showAvatarModal = ref(false)
const avatarUploading = ref(false)
const avatarDeleting = ref(false)

const availableCurrencies = ['EUR', 'USD', 'RUB', 'GBP', 'BTC']

// Language preference (synced via @nuxtjs/i18n module)
const { setLocale } = useI18n()

const selectedLanguage = computed({
  get: () => locale.value,
  set: (val) => {
    setLocale(val)
    updateLanguage(val)
  }
})

// Currency preference (localStorage, shared with useBtcPrice)
const selectedCurrency = useLocalPref('preferred_currency', 'EUR')

// Country
const ISO_CODES = [
  'AD','AE','AF','AG','AI','AL','AM','AO','AQ','AR','AS','AT','AU','AW','AX','AZ',
  'BA','BB','BD','BE','BF','BG','BH','BI','BJ','BL','BM','BN','BO','BQ','BR','BS',
  'BT','BV','BW','BY','BZ','CA','CC','CD','CF','CG','CH','CI','CK','CL','CM','CN',
  'CO','CR','CU','CV','CW','CX','CY','CZ','DE','DJ','DK','DM','DO','DZ','EC','EE',
  'EG','EH','ER','ES','ET','FI','FJ','FK','FM','FO','FR','GA','GB','GD','GE','GF',
  'GG','GH','GI','GL','GM','GN','GP','GQ','GR','GS','GT','GU','GW','GY','HK','HM',
  'HN','HR','HT','HU','ID','IE','IL','IM','IN','IO','IQ','IR','IS','IT','JE','JM',
  'JO','JP','KE','KG','KH','KI','KM','KN','KP','KR','KW','KY','KZ','LA','LB','LC',
  'LI','LK','LR','LS','LT','LU','LV','LY','MA','MC','MD','ME','MF','MG','MH','MK',
  'ML','MM','MN','MO','MP','MQ','MR','MS','MT','MU','MV','MW','MX','MY','MZ','NA',
  'NC','NE','NF','NG','NI','NL','NO','NP','NR','NU','NZ','OM','PA','PE','PF','PG',
  'PH','PK','PL','PM','PN','PR','PS','PT','PW','PY','QA','RE','RO','RS','RU','RW',
  'SA','SB','SC','SD','SE','SG','SH','SI','SJ','SK','SL','SM','SN','SO','SR','SS',
  'ST','SV','SX','SY','SZ','TC','TD','TF','TG','TH','TJ','TK','TL','TM','TN','TO',
  'TR','TT','TV','TW','TZ','UA','UG','UM','US','UY','UZ','VA','VC','VE','VG','VI',
  'VN','VU','WF','WS','YE','YT','ZA','ZM','ZW',
]

const codeToFlag = (code: string) =>
  code.toUpperCase().split('').map(c => String.fromCodePoint(c.charCodeAt(0) + 127397)).join('')

const COUNTRIES = ref<{ code: string; name: string; flag: string }[]>([])
const selectedCountry = ref('')
const countrySaving = ref(false)

watch(() => authStore.profile?.country_code, (code) => {
  if (code !== undefined && !countrySaving.value) {
    selectedCountry.value = code || ''
  }
}, { immediate: true })

onMounted(() => {
  const regionNames = new Intl.DisplayNames([locale.value], { type: 'region' })
  COUNTRIES.value = ISO_CODES
    .map(code => ({ code, name: regionNames.of(code) || code, flag: codeToFlag(code) }))
    .sort((a, b) => a.name.localeCompare(b.name, locale.value))
})

const saveCountry = async () => {
  countrySaving.value = true
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ country_code: selectedCountry.value })
    })
    if (authStore.profile) authStore.profile.country_code = selectedCountry.value
    showSuccess(t('profile.preferences.country_updated'))
  } catch {
    showError(t('profile.preferences.country_update_failed'))
  } finally {
    countrySaving.value = false
  }
}

const updateLanguage = async (code: string) => {
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: { preferred_language: code }
    })
  } catch (error) {
    console.error('Failed to save language preference:', error)
  }
}

const updateCurrency = async () => {
  try {
    await authStore.ensureToken()
    await $fetch('/api/v1/profiles/me/preferences/', {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        preferred_currency: selectedCurrency.value
      })
    })
    showSuccess(t('profile.preferences.currency_updated'))
  } catch (error) {
    console.error('Failed to update currency:', error)
    showError(t('profile.preferences.currency_update_failed'))
  }
}

// Avatar upload
const uploadAvatar = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  const file = input.files[0]
  if (file.size > 10 * 1024 * 1024) {
    showError(t('profile.photos.error_file_too_large'))
    return
  }

  avatarUploading.value = true

  try {
    await authStore.ensureToken()

    const formData = new FormData()
    formData.append('image', file)

    const response = await $fetch<{ url: string }>('/api/v1/profiles/me/avatar/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    if (authStore.user?.profile) {
      authStore.user.profile.avatar_url = response.url
    }
    showSuccess(t('profile.photos.avatar_uploaded'))
    showAvatarModal.value = false
  } catch (error: any) {
    console.error('Avatar upload error:', error)
    showError(error.data?.error || t('profile.photos.upload_failed'))
  } finally {
    avatarUploading.value = false
    input.value = ''
  }
}

// Avatar delete
const deleteAvatar = async () => {
  avatarDeleting.value = true

  try {
    await authStore.ensureToken()

    await $fetch('/api/v1/profiles/me/avatar/', {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    if (authStore.user?.profile) {
      authStore.user.profile.avatar_url = null
    }
    showSuccess(t('profile.photos.avatar_deleted'))
    showAvatarModal.value = false
  } catch (error: any) {
    console.error('Avatar delete error:', error)
    showError(error.data?.error || t('profile.photos.delete_failed'))
  } finally {
    avatarDeleting.value = false
  }
}

</script>
