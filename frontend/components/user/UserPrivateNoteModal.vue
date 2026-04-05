<template>
  <Modal
    v-model="visible"
    :title="t('user_profile.private_note_title')"
    :icon="Edit"
    icon-class="text-secondary-600"
    size="md"
    @close="closeNoteModal"
  >
    <div class="space-y-4">
      <div>
        <label for="private-note" class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
          {{ t('user_profile.note_about', { name: profile.display_name || profile.hna }) }}
        </label>
        <textarea
          id="private-note"
          v-model="editingNote"
          :placeholder="t('user_profile.note_placeholder')"
          class="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          rows="5"
        ></textarea>
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
          {{ t('user_profile.note_private_desc') }}
        </p>
      </div>
    </div>

    <template #footer>
      <button
        @click="closeNoteModal"
        class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700"
      >
        {{ t('user_profile.cancel') }}
      </button>
      <button
        v-if="editingNote !== privateNote"
        @click="savePrivateNote"
        :disabled="savingNote"
        class="px-4 py-2 bg-secondary-500 text-white font-medium rounded-lg hover:bg-secondary-600 flex items-center gap-2"
      >
        <Loader2 v-if="savingNote" class="w-4 h-4 animate-spin" />
        {{ t('user_profile.save_note') }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { Edit, Loader2 } from 'lucide-vue-next'

const props = defineProps<{ profile: any; cri: string; modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; 'note-changed': [string] }>()

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const privateNote = ref('')
const editingNote = ref('')
const savingNote = ref(false)

const loadPrivateNote = async () => {
  try {
    await authStore.ensureToken()
    const response = await $fetch(`/api/v1/profiles/${props.cri}/note/`, {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    if (response && (response as any).note) {
      privateNote.value = (response as any).note
      emit('note-changed', privateNote.value)
    }
  } catch (err: any) {
    if (err.statusCode !== 404 && err.status !== 404) {
      console.error('Error loading private note:', err)
    }
  }
}

const savePrivateNote = async () => {
  savingNote.value = true
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/profiles/${props.cri}/note/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        note: editingNote.value
      }
    })
    privateNote.value = editingNote.value
    visible.value = false
    emit('note-changed', privateNote.value)
    toastStore.success(t('user_profile.note_saved'))
  } catch (err) {
    console.error('Failed to save note:', err)
    toastStore.error(t('user_profile.note_save_error'))
  } finally {
    savingNote.value = false
  }
}

const closeNoteModal = () => {
  visible.value = false
  editingNote.value = privateNote.value
}

// Load note on mount if authenticated
onMounted(async () => {
  if (authStore.isAuthenticated) {
    await loadPrivateNote()
  }
})

watch(visible, (show) => {
  if (show) {
    editingNote.value = privateNote.value
  }
})
</script>
