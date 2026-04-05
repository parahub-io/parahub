<template>
  <div class="space-y-4">
    <!-- Rating summary -->
    <div v-if="reviews.length > 0" class="bg-neutral-50 dark:bg-neutral-800 p-4">
      <div class="flex items-center gap-4">
        <div class="text-center">
          <div class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{{ avgRating }}</div>
          <div class="flex items-center justify-center gap-0.5 my-1">
            <span v-for="s in 5" :key="s" class="text-lg" :class="s <= Math.round(Number(avgRating)) ? 'text-primary' : 'text-neutral-300 dark:text-neutral-600'">★</span>
          </div>
          <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('map.panel.reviews_avg', { avg: avgRating }) }}</div>
        </div>
        <div class="flex-1 space-y-1">
          <div v-for="star in [5,4,3,2,1]" :key="star" class="flex items-center gap-2">
            <span class="text-xs text-neutral-500 dark:text-neutral-400 w-3">{{ star }}</span>
            <span class="text-xs text-primary">★</span>
            <div class="flex-1 bg-neutral-200 dark:bg-neutral-700 h-1.5 rounded-full overflow-hidden">
              <div
                class="h-full bg-primary rounded-full transition-all"
                :style="{ width: ratingDistribution[star] > 0 ? `${(ratingDistribution[star] / reviews.length) * 100}%` : '0%' }"
              />
            </div>
            <span class="text-xs text-neutral-500 dark:text-neutral-400 w-4 text-right">{{ ratingDistribution[star] }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Write review form -->
    <div v-if="authStore.isAuthenticated && !userReview" class="border border-neutral-200 dark:border-neutral-700 p-4 space-y-3">
      <h4 class="font-semibold text-sm text-neutral-900 dark:text-neutral-100">{{ $t('map.panel.review_write') }}</h4>

      <!-- WoT gate -->
      <UiAlert v-if="!canReview" variant="warning">{{ $t('map.panel.review_wot_required') }}</UiAlert>

      <template v-else>
        <!-- Star input -->
        <div>
          <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-1">{{ $t('map.panel.review_your_rating') }}</p>
          <div class="flex gap-1">
            <button
              v-for="s in 5"
              :key="s"
              type="button"
              @click="newRating = s"
              @mouseenter="hoverRating = s"
              @mouseleave="hoverRating = 0"
              class="text-2xl leading-none transition-colors"
              :class="s <= (hoverRating || newRating) ? 'text-primary' : 'text-neutral-300 dark:text-neutral-600'"
            >★</button>
          </div>
        </div>

        <!-- Text -->
        <textarea
          id="review-text"
          v-model="newText"
          rows="3"
          class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100 resize-none"
          :placeholder="$t('map.panel.review_comment_placeholder')"
          :aria-label="$t('map.panel.review_comment_placeholder')"
        />

        <button
          @click="submitReview"
          :disabled="newRating === 0 || submitting"
          class="w-full btn-primary btn-sm"
        >
          {{ submitting ? $t('map.panel.review_submitting') : $t('map.panel.review_submit') }}
        </button>
      </template>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && reviews.length === 0" class="text-center py-6 text-neutral-500 dark:text-neutral-400 text-sm">
      {{ $t('map.panel.reviews_empty') }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-4 text-neutral-400 text-sm">...</div>

    <!-- Review list -->
    <div v-for="review in reviews" :key="review.id" class="border-b border-neutral-100 dark:border-neutral-800 pb-4 last:border-0">
      <!-- Review header -->
      <div class="flex items-start justify-between gap-2 mb-1">
        <div>
          <span class="text-sm font-medium text-neutral-900 dark:text-neutral-100">{{ review.author_display_name || review.author_hna?.split('@')[0] }}</span>
          <span v-if="review.wot_count_snapshot >= 2" class="ml-1.5 text-xs text-secondary dark:text-secondary-400" title="WoT verified">✓</span>
        </div>
        <span class="text-xs text-neutral-400 dark:text-neutral-500 flex-shrink-0">{{ formatDate(review.created_at) }}</span>
      </div>

      <!-- Stars -->
      <div class="flex gap-0.5 mb-1.5">
        <span v-for="s in 5" :key="s" class="text-base" :class="s <= review.rating ? 'text-primary' : 'text-neutral-200 dark:text-neutral-700'">★</span>
      </div>

      <!-- Text -->
      <p v-if="review.text" class="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">{{ review.text }}</p>

      <!-- Own review actions -->
      <div v-if="isOwnReview(review)" class="flex gap-3 mt-2">
        <button
          v-if="editingReviewId !== review.id"
          @click="startEditReview(review)"
          class="text-xs text-link"
        >{{ $t('map.panel.review_edit') }}</button>
        <button
          @click="deleteReview(review)"
          class="text-xs"
          :class="pendingDeleteReviewId === review.id ? 'text-white bg-error px-2 py-0.5 rounded' : 'text-red-500 hover:underline'"
        >{{ pendingDeleteReviewId === review.id ? $t('common.confirm') + '?' : $t('map.panel.review_delete') }}</button>
      </div>

      <!-- Edit form for own review -->
      <div v-if="editingReviewId === review.id" class="mt-2 space-y-2">
        <div class="flex gap-1">
          <button
            v-for="s in 5"
            :key="s"
            type="button"
            @click="editRating = s"
            class="text-xl"
            :class="s <= editRating ? 'text-primary' : 'text-neutral-300 dark:text-neutral-600'"
          >★</button>
        </div>
        <textarea
          :id="'review-edit-' + review.id"
          v-model="editText"
          rows="2"
          class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100 resize-none"
          :aria-label="$t('map.panel.review_edit')"
        />
        <div class="flex gap-2">
          <button @click="saveEditReview(review)" :disabled="editRating === 0 || submitting" class="btn-primary btn-sm text-xs">{{ $t('map.panel.save') }}</button>
          <button @click="editingReviewId = null" class="text-xs px-3 py-1 text-neutral-500 hover:text-neutral-700">{{ $t('map.panel.cancel') }}</button>
        </div>
      </div>

      <!-- Owner reply -->
      <div v-if="review.owner_reply" class="mt-2 pl-3 border-l-2 border-primary">
        <p class="text-xs text-neutral-500 dark:text-neutral-400 mb-0.5 font-medium">{{ $t('map.panel.review_owner_reply') }}</p>
        <p class="text-sm text-neutral-700 dark:text-neutral-300">{{ review.owner_reply }}</p>
      </div>

      <!-- Owner reply form (for establishment owner) -->
      <div v-if="isEstablishmentOwner && !review.owner_reply && replyingToReviewId !== review.id" class="mt-2">
        <button @click="startReply(review)" class="text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
          {{ $t('map.panel.review_reply_write') }}
        </button>
      </div>
      <div v-if="replyingToReviewId === review.id" class="mt-2 space-y-2">
        <textarea
          :id="'review-reply-' + review.id"
          v-model="replyText"
          rows="2"
          class="w-full px-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-neutral-800 dark:text-neutral-100 resize-none"
          :placeholder="$t('map.panel.review_reply_placeholder')"
          :aria-label="$t('map.panel.review_reply_write')"
        />
        <div class="flex gap-2">
          <button @click="saveReply(review)" :disabled="!replyText.trim() || submitting" class="btn-primary btn-sm text-xs">{{ $t('map.panel.review_reply_save') }}</button>
          <button @click="replyingToReviewId = null" class="text-xs px-3 py-1 text-neutral-500">{{ $t('map.panel.cancel') }}</button>
        </div>
      </div>
    </div>

    <!-- Load more -->
    <button
      v-if="hasMore && !loading"
      @click="loadMore"
      class="w-full py-2 text-sm text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
    >
      {{ $t('map.browse.load_more') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'

const props = defineProps<{
  establishmentId: string
  ownerId: string
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const toastStore = useToastStore()

const reviews = ref<any[]>([])
const loading = ref(false)
const submitting = ref(false)
const currentPage = ref(1)
const hasMore = ref(false)

// New review form
const newRating = ref(0)
const hoverRating = ref(0)
const newText = ref('')

// Edit
const editingReviewId = ref<string | null>(null)
const editRating = ref(0)
const editText = ref('')

const pendingDeleteReviewId = ref<string | null>(null)
let pendingDeleteReviewTimer: ReturnType<typeof setTimeout> | null = null

// Owner reply
const replyingToReviewId = ref<string | null>(null)
const replyText = ref('')

// WoT capability (optimistic: allow unless 403 from server)
const canReview = ref(true)

const userReview = computed(() => {
  if (!authStore.profile) return null
  return reviews.value.find(r => r.author_id === authStore.profile?.id) || null
})

const isEstablishmentOwner = computed(() => {
  return authStore.profile?.id === props.ownerId
})

const avgRating = computed(() => {
  if (reviews.value.length === 0) return '0.0'
  const sum = reviews.value.reduce((acc, r) => acc + r.rating, 0)
  return (sum / reviews.value.length).toFixed(1)
})

const ratingDistribution = computed(() => {
  const dist: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }
  reviews.value.forEach(r => { dist[r.rating] = (dist[r.rating] || 0) + 1 })
  return dist
})

function isOwnReview(review: any) {
  return authStore.profile?.id === review.author_id
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

async function loadReviews(page = 1) {
  loading.value = true
  try {
    const data = await $fetch(`/api/v1/geo/establishments/${props.establishmentId}/reviews/?page=${page}`)
    if (page === 1) {
      reviews.value = (data as any).items || []
    } else {
      reviews.value.push(...((data as any).items || []))
    }
    const total = (data as any).count || 0
    hasMore.value = reviews.value.length < total
    currentPage.value = page
  } catch (e) {
    // silent
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  await loadReviews(currentPage.value + 1)
}

async function submitReview() {
  if (newRating.value === 0 || submitting.value) return
  submitting.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch(`/api/v1/geo/establishments/${props.establishmentId}/reviews/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { rating: newRating.value, text: newText.value },
    })
    reviews.value.unshift(data as any)
    newRating.value = 0
    newText.value = ''
    toastStore.success(t('map.panel.review_success'))
  } catch (e: any) {
    if (e?.data?.detail?.includes('WoT') || e?.status === 403) {
      canReview.value = false
      toastStore.error(t('map.panel.review_wot_required'))
    } else if (e?.status === 409) {
      toastStore.error(t('map.panel.review_error'))
    } else {
      toastStore.error(t('map.panel.review_error'))
    }
  } finally {
    submitting.value = false
  }
}

function startEditReview(review: any) {
  editingReviewId.value = review.id
  editRating.value = review.rating
  editText.value = review.text
}

async function saveEditReview(review: any) {
  if (editRating.value === 0 || submitting.value) return
  submitting.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch(`/api/v1/geo/establishments/${props.establishmentId}/reviews/${review.id}/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { rating: editRating.value, text: editText.value },
    })
    const idx = reviews.value.findIndex(r => r.id === review.id)
    if (idx !== -1) reviews.value[idx] = data as any
    editingReviewId.value = null
    toastStore.success(t('map.panel.review_updated'))
  } catch {
    toastStore.error(t('map.panel.review_error'))
  } finally {
    submitting.value = false
  }
}

async function deleteReview(review: any) {
  if (pendingDeleteReviewId.value !== review.id) {
    pendingDeleteReviewId.value = review.id
    if (pendingDeleteReviewTimer) clearTimeout(pendingDeleteReviewTimer)
    pendingDeleteReviewTimer = setTimeout(() => { pendingDeleteReviewId.value = null }, 3000)
    return
  }
  pendingDeleteReviewId.value = null
  if (pendingDeleteReviewTimer) clearTimeout(pendingDeleteReviewTimer)
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/geo/establishments/${props.establishmentId}/reviews/${review.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    reviews.value = reviews.value.filter(r => r.id !== review.id)
    toastStore.success(t('map.panel.review_deleted'))
  } catch {
    toastStore.error(t('map.panel.review_error'))
  }
}

function startReply(review: any) {
  replyingToReviewId.value = review.id
  replyText.value = ''
}

async function saveReply(review: any) {
  if (!replyText.value.trim() || submitting.value) return
  submitting.value = true
  try {
    await authStore.ensureToken()
    const data = await $fetch(`/api/v1/geo/establishments/${props.establishmentId}/reviews/${review.id}/reply/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` },
      body: { owner_reply: replyText.value },
    })
    const idx = reviews.value.findIndex(r => r.id === review.id)
    if (idx !== -1) reviews.value[idx] = data as any
    replyingToReviewId.value = null
    toastStore.success(t('map.panel.review_reply_saved'))
  } catch {
    toastStore.error(t('map.panel.review_error'))
  } finally {
    submitting.value = false
  }
}

onMounted(() => loadReviews())
</script>
