<template>
  <Modal
    :model-value="modelValue"
    :title="$t('people_picker.title')"
    :icon="Users"
    size="lg"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="space-y-3">
      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 dark:text-neutral-500 pointer-events-none" />
        <input
          ref="inputRef"
          v-model="query"
          type="search"
          :placeholder="$t('people_picker.placeholder')"
          class="w-full pl-9 pr-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
      </div>

      <p v-if="caption" class="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {{ caption }}
      </p>

      <div v-if="busy" class="flex justify-center py-8">
        <Loader2 class="w-6 h-6 animate-spin text-neutral-400 dark:text-neutral-500" />
      </div>

      <div
        v-else-if="rows.length"
        class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden divide-y divide-neutral-200 dark:divide-neutral-700 max-h-[50vh] overflow-y-auto"
      >
        <button
          v-for="person in rows"
          :key="person.id"
          type="button"
          class="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          @click="choose(person)"
        >
          <img
            v-if="person.avatar_url"
            :src="person.avatar_url"
            :alt="personLabel(person)"
            class="w-10 h-10 rounded-full object-cover flex-shrink-0"
          />
          <div
            v-else
            class="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center flex-shrink-0"
          >
            <span class="text-sm font-bold text-black">{{ personInitials(person) }}</span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
              {{ personLabel(person) }}
            </div>
            <div class="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate">{{ person.hna }}</div>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <UiBadge v-if="person.is_verified_wot" variant="success" type="soft" size="sm" class="gap-1">
              <Shield class="w-3 h-3" />{{ $t('user_profile.verified') }}
            </UiBadge>
            <Users
              v-if="person.is_partner"
              class="w-4 h-4 text-neutral-400 dark:text-neutral-500"
              :aria-label="$t('people_picker.partners')"
            />
          </div>
        </button>
      </div>

      <!-- A modal is the one place a bare centred line beats the page-level
           empty state: there is no page to fill. The one thing left to do with
           a person who is not here yet is invite them, so the empty state ends
           on that action instead of a dead end. -->
      <div v-else class="text-center py-8">
        <p class="text-sm text-neutral-500 dark:text-neutral-400">
          {{ isSearch ? $t('people_picker.empty') : $t('people_picker.no_partners') }}
        </p>
        <UiButton variant="primary" size="sm" :icon="UserPlus" class="mt-3" @click="invite">
          {{ $t('people_picker.invite') }}
        </UiButton>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
/**
 * Reusable people picker: partners first, everyone else one query away.
 *
 * Picking a person only emits — where that leads is the caller's business (the
 * site menu walks to their profile). Verification, payment and every other act
 * on a person happens on `/@name`, never here.
 */
import { ref, computed, watch, nextTick } from 'vue'
import { Users, Search, Shield, Loader2, UserPlus } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'
import type { QuickPartner } from '~/composables/usePartnersQuickList'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [person: QuickPartner]
  invite: []
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const { items: partners, loading: partnersLoading, fetch: fetchPartners } = usePartnersQuickList()

const query = ref('')
const results = ref<QuickPartner[]>([])
const searching = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const isSearch = computed(() => query.value.trim().length >= 2)
const rows = computed(() => (isSearch.value ? results.value : partners.value))
const busy = computed(() => (isSearch.value ? searching.value : partnersLoading.value))
// Captions a list; with no partners to caption it would only label an empty state
const caption = computed(() => (isSearch.value || !partners.value.length ? '' : t('people_picker.partners')))

const personLabel = (person: QuickPartner) => person.display_name || person.hna
const personInitials = (person: QuickPartner) => {
  const name = personLabel(person)
  const parts = name.split(' ')
  if (parts.length >= 2) return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
  return name.substring(0, 2).toUpperCase()
}

const runSearch = async () => {
  const q = query.value.trim()
  if (q.length < 2) {
    results.value = []
    return
  }
  searching.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch<{ items: QuickPartner[] }>(
      `/api/v1/profiles/search/?q=${encodeURIComponent(q)}&page_size=10`,
      {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
      },
    )
    // A slower earlier query must not overwrite what the current one found
    if (query.value.trim() === q) results.value = data.items || []
  } catch {
    if (query.value.trim() === q) results.value = []
  } finally {
    searching.value = false
  }
}

watch(query, () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runSearch, 300)
})

watch(() => props.modelValue, async (open) => {
  if (!open) {
    query.value = ''
    results.value = []
    return
  }
  fetchPartners()
  await nextTick()
  inputRef.value?.focus()
})

const choose = (person: QuickPartner) => {
  emit('select', person)
  emit('update:modelValue', false)
}

// Inviting owns no state here either: the picker closes and the caller opens
// whatever it uses to invite (the site menu opens <InviteModal>).
const invite = () => {
  emit('update:modelValue', false)
  emit('invite')
}
</script>
