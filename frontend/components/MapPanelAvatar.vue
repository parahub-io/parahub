<template>
  <div class="px-4 pt-2 space-y-4">
    <!-- Own Avatar Controls -->
    <div v-if="contentType === 'own_avatar'" class="space-y-4">
      <!-- Speech Bubble Input -->
      <div>
        <label class="block text-sm font-medium mb-2 flex items-center gap-2 dark:text-neutral-100">
          <MessageSquare :size="16" />
          {{ t('map.presence.say_something') }}
        </label>
        <div class="flex gap-2">
          <input
            ref="speechInputRef"
            v-model="speechText"
            type="text"
            maxlength="200"
            :placeholder="t('map.presence.type_message')"
            :aria-label="t('map.presence.say_something')"
            class="flex-1 px-3 py-2 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            @keyup.enter="sendSpeechBubble"
          />
          <UiButton
            variant="secondary"
            size="sm"
            :icon="Send"
            icon-only
            :disabled="!speechText.trim()"
            :aria-label="t('map.presence.send_message')"
            @click="sendSpeechBubble"
          />
        </div>
        <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ t('map.presence.char_count', { count: speechText.length }) }}</div>
      </div>

      <!-- Action Buttons (LPC Animations) -->
      <div>
        <label class="block text-sm font-medium mb-2 dark:text-neutral-100">{{ t('map.presence.actions') }} <span class="text-neutral-400 dark:text-neutral-500 font-normal">(E/R/T)</span></label>
        <div class="grid grid-cols-3 gap-2">
          <button
            @click="setAvatarState('jumping')"
            class="flex flex-col items-center gap-1 p-2 border rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 dark:border-neutral-600 dark:text-neutral-100"
            :class="{ 'bg-secondary-50 border-secondary-600 dark:bg-secondary-900 dark:border-secondary-500': currentAvatarState === 'jumping' }"
          >
            <Zap :size="18" />
            <span class="text-xs">{{ t('map.presence.jump') }} (E)</span>
          </button>
          <button
            @click="setAvatarState('sitting')"
            class="flex flex-col items-center gap-1 p-2 border rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 dark:border-neutral-600 dark:text-neutral-100"
            :class="{ 'bg-secondary-50 border-secondary-600 dark:bg-secondary-900 dark:border-secondary-500': currentAvatarState === 'sitting' }"
          >
            <Armchair :size="18" />
            <span class="text-xs">{{ t('map.presence.sit') }} (R)</span>
          </button>
          <button
            @click="setAvatarState('emoting')"
            class="flex flex-col items-center gap-1 p-2 border rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800 dark:border-neutral-600 dark:text-neutral-100"
            :class="{ 'bg-secondary-50 border-secondary-600 dark:bg-secondary-900 dark:border-secondary-500': currentAvatarState === 'emoting' }"
          >
            <Hand :size="18" />
            <span class="text-xs">{{ t('map.presence.emote') }} (T)</span>
          </button>
        </div>
      </div>

      <!-- Avatar Type Selector -->
      <div>
        <label class="block text-sm font-medium mb-2 dark:text-neutral-100">{{ t('map.presence.avatar_type') }}</label>
        <select
          v-model="selectedAvatarType"
          @change="onAvatarTypeChange"
          class="w-full px-3 py-2 bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-600 rounded-lg text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        >
          <option value="p0">{{ t('map.presence.p0') }}</option>
          <option value="p1">{{ t('map.presence.p1') }}</option>
          <option value="p2">{{ t('map.presence.p2') }}</option>
          <option value="p3">{{ t('map.presence.p3') }}</option>
          <option value="p4">{{ t('map.presence.p4') }}</option>
        </select>
      </div>
    </div>

    <!-- Other Avatar Quick View (Compact) -->
    <div v-else-if="contentType === 'other_avatar'" class="space-y-3">
      <!-- Items sections -->
      <div v-if="avatarItemsLoading" class="flex justify-center py-4">
        <div class="w-5 h-5 border-2 border-secondary-600 border-t-transparent rounded-full animate-spin"></div>
      </div>

      <template v-else>
        <!-- Selling items -->
        <div v-if="avatarOfferItems.length > 0" class="space-y-2">
          <div class="flex items-center gap-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wide">
            <Package :size="12" />
            {{ t('map.presence.selling') }} ({{ avatarOfferItems.length }})
          </div>
          <div class="flex flex-wrap gap-1.5">
            <div
              v-for="item in avatarOfferItems.slice(0, 8)"
              :key="item.id"
              class="w-10 h-10 rounded bg-neutral-100 dark:bg-neutral-700 overflow-hidden cursor-pointer hover:ring-2 hover:ring-secondary-500 transition"
              :title="item.title"
              @click="openItemOnMarket(item.slug || item.id)"
            >
              <img
                v-if="item.images?.[0]?.url"
                :src="item.images[0].url"
                :alt="item.title"
                class="w-full h-full object-cover"
              />
              <div v-else class="w-full h-full flex items-center justify-center text-neutral-400">
                <Package :size="16" />
              </div>
            </div>
            <div
              v-if="avatarOfferItems.length > 8"
              class="w-10 h-10 rounded bg-secondary-100 dark:bg-secondary-900 flex items-center justify-center text-xs font-medium text-secondary-600 dark:text-secondary-300 cursor-pointer hover:bg-secondary-200 dark:hover:bg-secondary-800 transition"
              @click="router.push(localePath(`/u/${avatarData?.profile_hna?.split('@')[0] || avatarData?.profile_id}`))"
            >
              +{{ avatarOfferItems.length - 8 }}
            </div>
          </div>
        </div>

        <!-- Wanting items -->
        <div v-if="avatarRequestItems.length > 0" class="space-y-2">
          <div class="flex items-center gap-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wide">
            <Search :size="12" />
            {{ t('map.presence.looking_for') }} ({{ avatarRequestItems.length }})
          </div>
          <div class="flex flex-wrap gap-1.5">
            <div
              v-for="item in avatarRequestItems.slice(0, 8)"
              :key="item.id"
              class="w-10 h-10 rounded bg-neutral-100 dark:bg-neutral-700 overflow-hidden cursor-pointer hover:ring-2 hover:ring-success transition"
              :title="item.title"
              @click="openItemOnMarket(item.slug || item.id)"
            >
              <img
                v-if="item.images?.[0]?.url"
                :src="item.images[0].url"
                :alt="item.title"
                class="w-full h-full object-cover"
              />
              <div v-else class="w-full h-full flex items-center justify-center text-neutral-400">
                <Search :size="16" />
              </div>
            </div>
            <div
              v-if="avatarRequestItems.length > 8"
              class="w-10 h-10 rounded bg-success-50 dark:bg-success-900 flex items-center justify-center text-xs font-medium text-success dark:text-success-300 cursor-pointer hover:bg-success-100 dark:hover:bg-success-800 transition"
              @click="router.push(localePath(`/u/${avatarData?.profile_hna?.split('@')[0] || avatarData?.profile_id}`))"
            >
              +{{ avatarRequestItems.length - 8 }}
            </div>
          </div>
        </div>

        <!-- No items message -->
        <div v-if="avatarOfferItems.length === 0 && avatarRequestItems.length === 0" class="text-center py-3 text-sm text-neutral-500 dark:text-neutral-400">
          {{ t('map.presence.no_items_yet') }}
        </div>
      </template>

      <!-- View Profile button -->
      <UiButton
        variant="secondary"
        :icon="User"
        :to="localePath(`/u/${avatarData?.profile_hna?.split('@')[0] || avatarData?.profile_id}`)"
        class="w-full"
      >
        {{ t('map.presence.view_full_profile') }}
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { MessageSquare, Send, Zap, Hand, Armchair, Package, Search, User } from 'lucide-vue-next'
import type { AvatarState, AvatarType } from '~/composables/useMapPresence'

const router = useRouter()
const localePath = useLocalePath()
const { t } = useI18n()

const props = defineProps<{
  contentType: 'own_avatar' | 'other_avatar'
  avatarData: any
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'avatar-type-change', type: AvatarType): void
}>()

// Speech bubble
const speechText = ref('')
const speechInputRef = ref<HTMLInputElement | null>(null)

// Avatar state
const localAvatarState = ref<AvatarState>('idle')
const selectedAvatarType = ref<AvatarType>('p1')

const currentAvatarState = computed(() => {
  return props.avatarData?.currentAvatarState || localAvatarState.value
})

// Avatar items (other_avatar)
const avatarItemsLoading = ref(false)
const avatarOfferItems = ref<any[]>([])
const avatarRequestItems = ref<any[]>([])

function sendSpeechBubble() {
  const text = speechText.value.trim()
  if (!text || !props.avatarData?.setSpeechBubble) return
  props.avatarData.setSpeechBubble(text)

  setTimeout(() => {
    if (speechText.value === text) {
      speechText.value = ''
      props.avatarData.setSpeechBubble('')
    }
  }, 30000)
}

function setAvatarState(state: AvatarState) {
  if (!props.avatarData?.setState) return

  if (state === 'sitting' && currentAvatarState.value === 'sitting') {
    props.avatarData.setState('idle')
    return
  }

  if ((state === 'jumping' && currentAvatarState.value === 'jumping') ||
      (state === 'emoting' && currentAvatarState.value === 'emoting')) {
    return
  }

  props.avatarData.setState(state)

  if (state === 'jumping') {
    setTimeout(() => {
      if (currentAvatarState.value === 'jumping') {
        props.avatarData.setState('idle')
      }
    }, 600)
  } else if (state === 'emoting') {
    setTimeout(() => {
      if (currentAvatarState.value === 'emoting') {
        props.avatarData.setState('idle')
      }
    }, 400)
  }
}

function onAvatarTypeChange() {
  emit('avatar-type-change', selectedAvatarType.value)
}

async function fetchAvatarItems(profileId: string) {
  if (!profileId) return

  avatarItemsLoading.value = true
  avatarOfferItems.value = []
  avatarRequestItems.value = []

  try {
    const [offersRes, requestsRes] = await Promise.all([
      $fetch<any>(`/api/v1/items/?owner_id=${profileId}&item_type=CREDIT&is_active=true`),
      $fetch<any>(`/api/v1/items/?owner_id=${profileId}&item_type=DEBIT&is_active=true`)
    ])

    avatarOfferItems.value = offersRes.items || []
    avatarRequestItems.value = requestsRes.items || []
  } catch (error) {
    console.error('Failed to fetch avatar items:', error)
  } finally {
    avatarItemsLoading.value = false
  }
}

function openItemOnMarket(itemId: string) {
  emit('close')
  router.push(localePath(`/market/${itemId}`))
}

// Focus speech input (exposed to parent)
const focusSpeechInput = () => {
  nextTick(() => { speechInputRef.value?.focus() })
}
defineExpose({ focusSpeechInput })

// Fetch items when other avatar opens
watch(() => [props.contentType, props.avatarData?.profile_id], ([contentType, profileId]) => {
  if (contentType === 'other_avatar' && profileId) {
    fetchAvatarItems(profileId as string)
  } else {
    avatarOfferItems.value = []
    avatarRequestItems.value = []
  }
}, { immediate: true })
</script>
