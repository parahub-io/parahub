<template>
  <div class="py-6">
    <div class="max-w-4xl mx-auto px-4 sm:px-6">
      <!-- Back button -->
      <NuxtLink
        :to="localePath(`/org/${slug}`)"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-neutral-600 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg mb-4 transition-colors"
      >
        <ArrowLeft class="w-4 h-4" />
        {{ establishmentName || slug }}
      </NuxtLink>

      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-3">
            <ClipboardCheck class="w-7 h-7 text-yellow-600 dark:text-yellow-400" />
            {{ $t('treasury.audit.title') }}
          </h1>
          <p class="mt-1 text-neutral-500 dark:text-neutral-400 text-sm">
            {{ $t('treasury.audit.description') }}
          </p>
        </div>
      </div>

      <!-- Not authenticated -->
      <ClientOnly>
        <UiAlert v-if="!authStore.isAuthenticated" variant="info" class="mb-6">
          {{ $t('treasury.audit.sign_in') }}
        </UiAlert>
      </ClientOnly>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-600"></div>
      </div>

      <template v-else>
        <!-- ─── Summary Cards ─── -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
            <div class="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wide mb-1">
              {{ $t('treasury.audit.total_expenses') }}
            </div>
            <div class="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
              {{ totalExpensesAmount.toFixed(2) }}€
            </div>
            <div class="text-xs text-neutral-400 mt-1">{{ expenses.length }} {{ $t('treasury.audit.expenses').toLowerCase() }}</div>
          </div>
          <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
            <div class="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wide mb-1">
              {{ $t('treasury.audit.approved_total') }}
            </div>
            <div class="text-2xl font-bold text-green-600 dark:text-green-400">
              {{ approvedTotal.toFixed(2) }}€
            </div>
          </div>
          <div class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4">
            <div class="text-xs text-neutral-500 dark:text-neutral-400 uppercase tracking-wide mb-1">
              {{ $t('treasury.audit.pending_count') }}
            </div>
            <div class="text-2xl font-bold text-amber-600 dark:text-amber-400">
              {{ pendingCount }}
            </div>
          </div>
        </div>

        <!-- ─── Expense List ─── -->
        <section class="mb-8">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold text-neutral-800 dark:text-neutral-200 flex items-center gap-2">
              <Receipt class="w-5 h-5" />
              {{ $t('treasury.audit.expenses') }}
            </h2>
            <div class="flex items-center gap-2">
              <!-- Status filter -->
              <select
                v-model="statusFilter"
                class="text-xs border border-neutral-300 dark:border-neutral-600 rounded-lg px-2 py-1.5 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
              >
                <option value="">{{ $t('treasury.audit.filter_all') }}</option>
                <option value="DRAFT">{{ $t('treasury.audit.status_draft') }}</option>
                <option value="APPROVED">{{ $t('treasury.audit.status_approved') }}</option>
                <option value="REJECTED">{{ $t('treasury.audit.status_rejected') }}</option>
              </select>
              <!-- Add expense button (treasurer/owner/admin) -->
              <button
                v-if="canManage"
                @click="showExpenseModal = true; editingExpense = null"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-yellow-600 hover:bg-yellow-700 rounded-lg transition-colors"
              >
                <Plus class="w-3.5 h-3.5" />
                {{ $t('treasury.audit.add_expense') }}
              </button>
            </div>
          </div>

          <div v-if="filteredExpenses.length === 0" class="text-center py-8 text-neutral-500 dark:text-neutral-400 text-sm">
            <Receipt class="w-10 h-10 mx-auto mb-2 opacity-40" />
            {{ $t('treasury.audit.no_expenses') }}
          </div>

          <div v-else class="space-y-2">
            <div
              v-for="exp in filteredExpenses"
              :key="exp.id"
              class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4"
            >
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="font-medium text-neutral-900 dark:text-neutral-100 text-sm">
                      {{ exp.amount.toFixed(2) }}€
                    </span>
                    <span
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      :class="statusBadgeClass(exp.status)"
                    >
                      {{ $t(`treasury.audit.status_${exp.status.toLowerCase()}`) }}
                    </span>
                    <span v-if="exp.category_name" class="text-xs text-neutral-400">
                      {{ $t(`treasury.category.${exp.category_name.toLowerCase()}`, exp.category_name) }}
                    </span>
                  </div>
                  <p class="text-sm text-neutral-600 dark:text-neutral-400 truncate">
                    {{ exp.description }}
                  </p>
                  <div class="flex items-center gap-3 mt-1 text-xs text-neutral-400">
                    <span>{{ exp.date }}</span>
                    <span v-if="exp.created_by_hna">{{ exp.created_by_display_name || exp.created_by_hna?.split('@')[0] }}</span>
                    <a
                      v-if="exp.receipt_url"
                      :href="exp.receipt_url"
                      target="_blank"
                      class="text-yellow-600 dark:text-yellow-400 hover:underline flex items-center gap-0.5"
                    >
                      <ExternalLink class="w-3 h-3" />
                      Receipt
                    </a>
                  </div>
                </div>
                <div class="flex items-center gap-1.5 ml-3 shrink-0">
                  <!-- Edit (only DRAFT, only creator/treasurer/owner) -->
                  <button
                    v-if="exp.status === 'DRAFT' && canManage"
                    @click="startEdit(exp)"
                    class="p-1.5 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    :title="$t('treasury.audit.edit_expense')"
                  >
                    <Pencil class="w-4 h-4" />
                  </button>
                  <!-- Approve/Reject (only DRAFT, only auditor/owner/admin) -->
                  <template v-if="exp.status === 'DRAFT' && canApprove">
                    <button
                      @click="setExpenseStatus(exp.id, 'APPROVED')"
                      class="p-1.5 text-green-500 hover:text-green-700 dark:hover:text-green-400 transition-colors"
                      :title="$t('treasury.audit.approve')"
                    >
                      <Check class="w-4 h-4" />
                    </button>
                    <button
                      @click="setExpenseStatus(exp.id, 'REJECTED')"
                      class="p-1.5 text-red-500 hover:text-red-700 dark:hover:text-red-400 transition-colors"
                      :title="$t('treasury.audit.reject')"
                    >
                      <X class="w-4 h-4" />
                    </button>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ─── Budget vs Actual ─── -->
        <section v-if="budgetData && budgetData.medians.length > 0" class="mb-8">
          <h2 class="text-lg font-semibold text-neutral-800 dark:text-neutral-200 mb-4 flex items-center gap-2">
            <BarChart3 class="w-5 h-5" />
            {{ $t('treasury.audit.budget_vs_actual') }}
          </h2>
          <div class="space-y-3">
            <div
              v-for="cat in budgetVsActual"
              :key="cat.slug"
              class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-4"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="text-sm font-medium text-neutral-800 dark:text-neutral-200">
                  {{ $t(`treasury.category.${cat.slug}`, cat.name) }}
                </span>
                <div class="flex items-center gap-3 text-xs">
                  <span class="text-neutral-400">
                    {{ $t('treasury.audit.budget_pct') }}: {{ cat.median_percent.toFixed(0) }}%
                  </span>
                  <span class="font-medium text-neutral-700 dark:text-neutral-300">
                    {{ $t('treasury.audit.spent') }}: {{ cat.spent.toFixed(2) }}€
                  </span>
                </div>
              </div>
              <!-- Dual bar -->
              <div class="space-y-1">
                <div class="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-2 overflow-hidden">
                  <div
                    class="h-full rounded-full bg-yellow-500/40"
                    :style="{ width: cat.median_percent + '%' }"
                  ></div>
                </div>
                <div class="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-2 overflow-hidden">
                  <div
                    class="h-full rounded-full"
                    :class="cat.spentPercent > cat.median_percent ? 'bg-red-500' : 'bg-green-500'"
                    :style="{ width: Math.min(cat.spentPercent, 100) + '%' }"
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ─── Audit Log ─── -->
        <section>
          <button
            @click="showAuditLog = !showAuditLog"
            class="flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 mb-3"
          >
            <FileText class="w-4 h-4" />
            {{ $t('treasury.audit_log') }}
            <ChevronDown class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showAuditLog }" />
          </button>

          <div v-if="showAuditLog" class="space-y-2">
            <div v-if="loadingAudit" class="flex justify-center py-4">
              <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-yellow-600"></div>
            </div>
            <div v-else-if="auditLogs.length === 0" class="text-center py-4 text-neutral-400 text-sm">
              {{ $t('treasury.no_audit_entries') }}
            </div>
            <div
              v-for="log in auditLogs"
              :key="log.id"
              class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3 text-xs"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-neutral-700 dark:text-neutral-300">
                  {{ log.action.replace('_', ' ') }}
                </span>
                <span class="text-neutral-400 font-mono">
                  {{ formatDate(log.timestamp) }}
                </span>
              </div>
              <div class="text-neutral-500 dark:text-neutral-400">
                <span v-if="log.actor_hna">{{ log.actor_hna }}</span>
                <span v-else>system</span>
              </div>
              <div class="mt-1 font-mono text-[10px] text-neutral-400 break-all">
                {{ log.current_log_hash }}
              </div>
            </div>
          </div>
        </section>
      </template>

      <!-- ─── Add/Edit Expense Modal ─── -->
      <Teleport to="body">
        <div
          v-if="showExpenseModal"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          @click.self="showExpenseModal = false"
        >
          <div class="bg-white dark:bg-neutral-800 rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h3 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              {{ editingExpense ? $t('treasury.audit.edit_expense') : $t('treasury.audit.add_expense') }}
            </h3>

            <div class="space-y-3">
              <div>
                <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
                  {{ $t('treasury.audit.expense_amount') }}
                </label>
                <input
                  v-model.number="expenseForm.amount"
                  type="number"
                  step="0.01"
                  min="0"
                  class="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                />
              </div>
              <div>
                <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
                  {{ $t('treasury.audit.expense_description') }}
                </label>
                <textarea
                  v-model="expenseForm.description"
                  rows="2"
                  class="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                ></textarea>
              </div>
              <div>
                <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
                  {{ $t('treasury.audit.expense_date') }}
                </label>
                <input
                  v-model="expenseForm.date"
                  type="date"
                  class="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                />
              </div>
              <div>
                <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
                  {{ $t('treasury.audit.expense_category') }}
                </label>
                <select
                  v-model="expenseForm.category_id"
                  class="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                >
                  <option value="">{{ $t('treasury.audit.expense_no_category') }}</option>
                  <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                    {{ $t(`treasury.category.${cat.slug}`, cat.name) }}
                  </option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-neutral-600 dark:text-neutral-400 block mb-1">
                  {{ $t('treasury.audit.expense_receipt') }}
                </label>
                <input
                  v-model="expenseForm.receipt_url"
                  type="url"
                  placeholder="https://..."
                  class="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100"
                />
              </div>
            </div>

            <div class="flex justify-end gap-2 mt-5">
              <button
                @click="showExpenseModal = false"
                class="px-4 py-2 text-sm text-neutral-600 dark:text-neutral-400 hover:text-neutral-800 dark:hover:text-neutral-200"
              >
                {{ $t('treasury.audit.cancel') }}
              </button>
              <button
                @click="saveExpense"
                :disabled="!expenseForm.amount || !expenseForm.description || !expenseForm.date || savingExpense"
                class="px-4 py-2 text-sm font-medium text-white bg-yellow-600 hover:bg-yellow-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ savingExpense ? '...' : $t('treasury.audit.save') }}
              </button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  ClipboardCheck, ArrowLeft, Receipt, BarChart3, FileText,
  ChevronDown, Plus, Check, X, Pencil, ExternalLink
} from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()
const localePath = useLocalePath()
const authStore = useAuthStore()

const slug = computed(() => route.params.slug as string)

// ── State ──
const loading = ref(true)
const loadingAudit = ref(false)
const savingExpense = ref(false)
const establishmentName = ref('')

interface ExpenseItem {
  id: string
  category_id: string | null
  category_name: string | null
  created_by_id: string | null
  created_by_hna: string | null
  amount: number
  description: string
  receipt_url: string
  date: string
  status: string
  epoch_label: string
  created_at: string
}

interface CategoryItem {
  id: string
  name: string
  slug: string
  icon: string
  order: number
}

interface MedianItem {
  category_id: string
  slug: string
  name: string
  median_percent: number
  voter_count: number
}

interface BudgetDataT {
  medians: MedianItem[]
  total_eligible: number
  total_participants: number
}

interface AuditItem {
  id: string
  action: string
  actor_hna: string | null
  current_log_hash: string
  timestamp: string
}

const expenses = ref<ExpenseItem[]>([])
const categories = ref<CategoryItem[]>([])
const budgetData = ref<BudgetDataT | null>(null)
const auditLogs = ref<AuditItem[]>([])
const statusFilter = ref('')
const showAuditLog = ref(false)
const showExpenseModal = ref(false)
const editingExpense = ref<ExpenseItem | null>(null)

// Permissions
const canManage = ref(false)  // can create/edit expenses
const canApprove = ref(false)  // can approve/reject

const expenseForm = ref({
  amount: 0,
  description: '',
  date: new Date().toISOString().slice(0, 10),
  category_id: '',
  receipt_url: '',
})

// ── Computed ──
const filteredExpenses = computed(() => {
  if (!statusFilter.value) return expenses.value
  return expenses.value.filter(e => e.status === statusFilter.value)
})

const totalExpensesAmount = computed(() =>
  expenses.value.reduce((s, e) => s + e.amount, 0)
)

const approvedTotal = computed(() =>
  expenses.value.filter(e => e.status === 'APPROVED').reduce((s, e) => s + e.amount, 0)
)

const pendingCount = computed(() =>
  expenses.value.filter(e => e.status === 'DRAFT').length
)

const budgetVsActual = computed(() => {
  if (!budgetData.value) return []
  const approvedExpenses = expenses.value.filter(e => e.status === 'APPROVED')
  const totalApproved = approvedExpenses.reduce((s, e) => s + e.amount, 0)

  return budgetData.value.medians.map(m => {
    const catExpenses = approvedExpenses.filter(e => e.category_id === m.category_id)
    const spent = catExpenses.reduce((s, e) => s + e.amount, 0)
    const spentPercent = totalApproved > 0 ? (spent / totalApproved) * 100 : 0

    return {
      ...m,
      spent,
      spentPercent,
    }
  })
})

// ── Helpers ──
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'DRAFT': return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
    case 'APPROVED': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    case 'REJECTED': return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    default: return 'bg-neutral-100 text-neutral-600'
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function startEdit(exp: ExpenseItem) {
  editingExpense.value = exp
  expenseForm.value = {
    amount: exp.amount,
    description: exp.description,
    date: exp.date,
    category_id: exp.category_id || '',
    receipt_url: exp.receipt_url,
  }
  showExpenseModal.value = true
}

// ── API ──
const apiBase = computed(() => `/api/v1/treasury/${slug.value}`)

async function fetchEstablishment() {
  try {
    const data: any = await $fetch(`/api/v1/geo/establishments/${slug.value}/`)
    establishmentName.value = data.name
  } catch (e) {
    console.error('Failed to fetch establishment:', e)
  }
}

async function fetchCategories() {
  try {
    categories.value = await $fetch(`${apiBase.value}/categories/`)
  } catch (e) {
    console.error('Failed to fetch categories:', e)
  }
}

async function fetchBudget() {
  try {
    budgetData.value = await $fetch(`${apiBase.value}/current/`)
  } catch (e) {
    console.error('Failed to fetch budget:', e)
  }
}

async function fetchExpenses() {
  try {
    expenses.value = await $fetch(`${apiBase.value}/expenses/`)
  } catch (e) {
    console.error('Failed to fetch expenses:', e)
  }
}

async function checkPermissions() {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    const members: any = await $fetch(`/api/v1/geo/establishments/${slug.value}/members/`, {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })

    const profile = authStore.user
    if (!profile) return

    // Find our membership
    const myMembership = members.find((m: any) =>
      m.profile_id === profile.id || m.profile_hna === profile.username
    )

    // Check establishment owner
    const estData: any = await $fetch(`/api/v1/geo/establishments/${slug.value}/`)
    const isOwner = estData.owner_id === profile.id

    if (isOwner) {
      canManage.value = true
      canApprove.value = true
    } else if (myMembership) {
      canManage.value = myMembership.is_treasurer || myMembership.role === 'ADMIN'
      canApprove.value = myMembership.is_auditor || myMembership.role === 'ADMIN'
    }
  } catch (e) {
    console.error('Failed to check permissions:', e)
  }
}

async function saveExpense() {
  if (!authStore.isAuthenticated) return
  savingExpense.value = true
  try {
    await authStore.ensureToken()
    const body: any = {
      amount: expenseForm.value.amount,
      description: expenseForm.value.description,
      date: expenseForm.value.date,
      category_id: expenseForm.value.category_id || null,
      receipt_url: expenseForm.value.receipt_url,
    }

    if (editingExpense.value) {
      await $fetch(`${apiBase.value}/expenses/${editingExpense.value.id}/`, {
        method: 'PUT',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body,
      })
    } else {
      await $fetch(`${apiBase.value}/expenses/`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body,
      })
    }

    showExpenseModal.value = false
    editingExpense.value = null
    await fetchExpenses()
  } catch (e: any) {
    console.error('Failed to save expense:', e)
  } finally {
    savingExpense.value = false
  }
}

async function setExpenseStatus(expenseId: string, status: string) {
  if (!authStore.isAuthenticated) return
  try {
    await authStore.ensureToken()
    await $fetch(`${apiBase.value}/expenses/${expenseId}/status/`, {
      method: 'PUT',
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: { status },
    })
    await fetchExpenses()
  } catch (e: any) {
    console.error('Failed to update expense status:', e)
  }
}

async function fetchAuditLog() {
  loadingAudit.value = true
  try {
    const res: any = await $fetch(`${apiBase.value}/audit-log/`)
    auditLogs.value = res.items || []
  } catch (e) {
    console.error('Failed to fetch audit log:', e)
  } finally {
    loadingAudit.value = false
  }
}

// ── Lifecycle ──
onMounted(async () => {
  await fetchEstablishment()
  await Promise.all([fetchCategories(), fetchBudget(), fetchExpenses(), checkPermissions()])
  loading.value = false
})

watch(showAuditLog, (v) => {
  if (v && auditLogs.value.length === 0) {
    fetchAuditLog()
  }
})
</script>
