<template>
  <div class="py-6">
    <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
      <PageHeader
        :title="$t('contracts.title')"
        :create-label="$t('contracts.create_new')"
        @create="openCreateModal"
      />

      <!-- Tabs -->
      <UiTabs v-model="activeTab" :tabs="contractTabs" class="mb-6">
      <!-- Tab content -->
      <div class="mt-6">
        <div v-if="loading" class="text-center py-12" role="status" aria-live="polite">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100" aria-hidden="true"></div>
          <span class="sr-only">{{ $t('common.loading') }}</span>
        </div>

        <!-- Contract list -->
        <div v-else-if="filteredContracts.length > 0" class="space-y-3">
          <div
            v-for="contract in filteredContracts"
            :key="contract.id"
            class="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden"
          >
            <!-- Compact header (always visible) -->
            <div
              class="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
              @click="toggleExpand(contract.id)"
            >
              <!-- Status indicator -->
              <UiBadge
                :variant="contract.status === 'COMPLETED' ? 'secondary' : contract.status === 'SIGNED' ? 'success' : 'warning'"
                type="dot"
                size="sm"
              />

              <!-- Title + counterparty -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <h3 class="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
                    {{ contract.title }}
                  </h3>
                  <div v-if="contract.items?.length" class="flex gap-1 shrink-0">
                    <span
                      v-for="item in contract.items.slice(0, 2)"
                      :key="item.id"
                      class="inline-flex items-center gap-0.5 px-1.5 py-0 text-[10px] rounded border border-neutral-200 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400"
                    >
                      <span :class="item.type === 'CREDIT' ? 'text-offer-600 dark:text-offer-400' : 'text-want-600 dark:text-want-400'">{{ item.type === 'CREDIT' ? '↑' : '↓' }}</span>{{ item.title.slice(0, 15) }}{{ item.title.length > 15 ? '…' : '' }}
                    </span>
                    <span v-if="contract.items.length > 2" class="text-[10px] text-neutral-400">+{{ contract.items.length - 2 }}</span>
                  </div>
                </div>
                <div class="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {{ $t(contract.creator_id === authStore.activeProfile?.id ? 'contracts.with' : 'contracts.from') }}
                  {{ contract.creator_id === authStore.activeProfile?.id ? contract.partner_display_name : contract.creator_display_name }}
                  <span class="mx-1">·</span>
                  {{ formatDate(contract.created_at) }}
                  <template v-if="contract.arbiter_id">
                    <span class="mx-1">·</span>
                    <Scale class="w-3 h-3 inline -mt-0.5" />
                    {{ contract.arbiter_display_name }}
                  </template>
                </div>
              </div>

              <!-- Quick actions (visible without expanding) -->
              <div class="flex items-center gap-2 shrink-0" @click.stop>
                <button
                  v-if="canSign(contract)"
                  @click="openSignModal(contract)"
                  class="btn-primary btn-xs whitespace-nowrap"
                >
                  {{ $t('contracts.sign') }}
                </button>
                <button
                  v-if="canComplete(contract)"
                  @click="openCompleteModal(contract)"
                  class="btn-success btn-xs"
                >
                  {{ $t('contracts.complete') }}
                </button>
                <button
                  v-if="canCancel(contract)"
                  @click="promptCancelContract(contract)"
                  class="btn-outline-error btn-xs"
                >
                  {{ getCancelButtonText(contract) }}
                </button>
              </div>

              <!-- Expand chevron -->
              <ChevronDown
                class="w-4 h-4 text-neutral-400 transition-transform shrink-0"
                :class="{ 'rotate-180': expandedContracts.has(contract.id) }"
              />
            </div>

            <!-- Expanded details -->
            <div v-if="expandedContracts.has(contract.id)" class="border-t border-neutral-200 dark:border-neutral-700 px-4 py-4 space-y-4 font-mono text-sm">
              <div class="flex flex-col sm:flex-row gap-4 sm:gap-6">
                <div class="flex-1 space-y-4">
                  <!-- Parties -->
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                    <div>
                      <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-1">
                        {{ $t(contract.creator_id === authStore.activeProfile?.id ? 'contracts.with' : 'contracts.from') }}
                      </div>
                      <NuxtLink
                        :to="localePath(`/u/${contract.creator_id === authStore.activeProfile?.id ? (contract.partner_hna?.split('@')[0] || contract.partner_id) : (contract.creator_hna?.split('@')[0] || contract.creator_id)}`)"
                        class="text-link break-words"
                      >
                        {{ contract.creator_id === authStore.activeProfile?.id ? contract.partner_display_name : contract.creator_display_name }}
                      </NuxtLink>
                    </div>
                    <div v-if="contract.arbiter_id">
                      <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-1">
                        {{ $t('contracts.arbiter') }}
                      </div>
                      <NuxtLink :to="localePath(`/u/${contract.arbiter_hna?.split('@')[0] || contract.arbiter_id}`)" class="text-link break-words">
                        {{ contract.arbiter_display_name }}
                      </NuxtLink>
                      <NuxtLink :to="localePath(`/arbiters/${contract.arbiter_id}`)" class="text-link text-xs ml-1">
                        <Scale class="w-3 h-3 inline" />
                      </NuxtLink>
                    </div>
                  </div>

                  <!-- Linked items -->
                  <div v-if="contract.items?.length" class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
                    <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.items').toUpperCase() }}</div>
                    <div class="flex flex-wrap gap-1.5">
                      <span
                        v-for="item in contract.items"
                        :key="item.id"
                        class="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300"
                      >
                        <span :class="item.type === 'CREDIT' ? 'text-offer-600 dark:text-offer-400' : 'text-want-600 dark:text-want-400'">{{ item.type === 'CREDIT' ? '↑' : '↓' }}</span>
                        {{ item.title }}
                      </span>
                    </div>
                  </div>

                  <!-- Contract terms (native — stored server-side, party-only) -->
                  <div v-if="contract.document_text" class="border-t border-neutral-200 dark:border-neutral-700 pt-3">
                    <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.terms_label').toUpperCase() }}</div>
                    <div class="prose prose-sm dark:prose-invert max-w-none" v-html="contract.document_text_html"></div>
                  </div>

                  <!-- Technical data -->
                  <div class="border-t border-neutral-200 dark:border-neutral-700 pt-3 space-y-2">
                    <div class="flex items-start gap-2 text-xs">
                      <span class="text-neutral-400 dark:text-neutral-500 uppercase tracking-wider flex-shrink-0">SHA256:</span>
                      <span class="text-neutral-700 dark:text-neutral-300 break-all">{{ contract.file_sha256 }}</span>
                    </div>
                    <div class="flex items-center gap-2 text-xs">
                      <span class="text-neutral-400 dark:text-neutral-500 uppercase tracking-wider">{{ $t('contracts.created').toUpperCase() }}:</span>
                      <span class="text-neutral-700 dark:text-neutral-300">{{ formatDate(contract.created_at) }}</span>
                    </div>
                    <!-- OTS Anchoring -->
                    <div v-if="contract.timestamp_proof" class="flex items-center gap-2 text-xs">
                      <span class="text-neutral-400 dark:text-neutral-500 uppercase tracking-wider shrink-0">OTS:</span>
                      <span v-if="contract.timestamp_proof.bitcoin_block" class="text-amber-600 dark:text-amber-400 font-medium">
                        ₿ {{ $t('contracts.ots.block') }} #{{ contract.timestamp_proof.bitcoin_block }}
                      </span>
                      <span v-else class="text-neutral-400 dark:text-neutral-500 animate-pulse">
                        {{ $t('contracts.ots.pending') }}
                      </span>
                    </div>
                  </div>

                  <!-- Signature status -->
                  <div class="border-t border-neutral-200 dark:border-neutral-700 pt-3 space-y-2">
                    <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.signatures').toUpperCase() }}</div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3 text-xs">
                      <div :class="[
                        'flex items-center gap-2 px-2 sm:px-3 py-2 border rounded',
                        contract.creator_signed_at
                          ? 'border-green-500 dark:border-green-600 bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400'
                          : 'border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400'
                      ]">
                        <span class="text-lg leading-none flex-shrink-0">{{ contract.creator_signed_at ? '✓' : '○' }}</span>
                        <span class="break-words">{{ contract.creator_display_name }}<br>{{ contract.creator_signed_at ? $t('contracts.signed') : $t('contracts.pending') }}</span>
                      </div>
                      <div :class="[
                        'flex items-center gap-2 px-2 sm:px-3 py-2 border rounded',
                        contract.partner_signed_at
                          ? 'border-green-500 dark:border-green-600 bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400'
                          : 'border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400'
                      ]">
                        <span class="text-lg leading-none flex-shrink-0">{{ contract.partner_signed_at ? '✓' : '○' }}</span>
                        <span class="break-words">{{ contract.partner_display_name }}<br>{{ contract.partner_signed_at ? $t('contracts.signed') : $t('contracts.pending') }}</span>
                      </div>
                    </div>

                    <!-- Completion status (if signed) -->
                    <div v-if="contract.status === 'SIGNED' || contract.status === 'COMPLETED'" class="mt-3">
                      <div class="text-xs uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">{{ $t('contracts.completion').toUpperCase() }}</div>
                      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3 text-xs">
                        <div :class="[
                          'flex items-center gap-2 px-2 sm:px-3 py-2 border rounded',
                          contract.creator_completed_at
                            ? 'border-secondary dark:border-secondary-600 bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-400'
                            : 'border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400'
                        ]">
                          <span class="text-lg leading-none flex-shrink-0">{{ contract.creator_completed_at ? '✓' : '○' }}</span>
                          <span class="break-words">{{ contract.creator_display_name }}<br>{{ contract.creator_completed_at ? $t('contracts.completed_work') : $t('contracts.in_progress') }}</span>
                        </div>
                        <div :class="[
                          'flex items-center gap-2 px-2 sm:px-3 py-2 border rounded',
                          contract.partner_completed_at
                            ? 'border-secondary dark:border-secondary-600 bg-secondary-50 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-400'
                            : 'border-neutral-300 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400'
                        ]">
                          <span class="text-lg leading-none flex-shrink-0">{{ contract.partner_completed_at ? '✓' : '○' }}</span>
                          <span class="break-words">{{ contract.partner_display_name }}<br>{{ contract.partner_completed_at ? $t('contracts.completed_work') : $t('contracts.in_progress') }}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Verdict + Escalation section -->
                  <ContractVerdictSection
                    v-if="contract.status === 'SIGNED' || contract.status === 'COMPLETED'"
                    :contract="contract"
                    :submitting-verdict="submittingVerdictId === contract.id"
                    :rating-arbiter="ratingArbiterId === contract.id"
                    :escalating="escalatingId === contract.id"
                    @submit-verdict="submitVerdict"
                    @rate-arbiter="rateArbiter"
                    @escalate="promptEscalate"
                  />
                </div>

                <!-- Actions column -->
                <div class="flex flex-col gap-2 w-full sm:w-auto sm:min-w-[160px]">
                  <button
                    v-if="canSign(contract)"
                    @click="openSignModal(contract)"
                    class="btn-primary btn-sm whitespace-nowrap"
                  >
                    {{ $t('contracts.sign') }}
                  </button>
                  <button
                    v-if="canComplete(contract)"
                    @click="openCompleteModal(contract)"
                    class="btn-success btn-sm"
                  >
                    {{ $t('contracts.complete') }}
                  </button>
                  <button
                    v-if="contract.status === 'SIGNED' || contract.status === 'COMPLETED'"
                    @click="exportProof(contract.id)"
                    class="btn-outline btn-sm flex items-center justify-center gap-2 whitespace-nowrap"
                    :disabled="exportingContractId === contract.id"
                  >
                    <Download v-if="exportingContractId !== contract.id" class="w-4 h-4 flex-shrink-0" />
                    <div v-else class="w-4 h-4 border-2 border-neutral-300 border-t-neutral-900 dark:border-neutral-600 dark:border-t-neutral-100 rounded-full animate-spin flex-shrink-0"></div>
                    <span class="truncate">{{ $t('contracts.export_proof') }}</span>
                  </button>
                  <!-- Arbitration button -->
                  <button
                    v-if="canInitiateArbitration(contract)"
                    @click="promptArbitration(contract)"
                    class="btn-outline-warning btn-sm flex items-center justify-center gap-2"
                    :disabled="initiatingArbitrationId === contract.id"
                  >
                    <div v-if="initiatingArbitrationId === contract.id" class="w-4 h-4 border-2 border-warning border-t-transparent rounded-full animate-spin flex-shrink-0"></div>
                    <Scale v-else class="w-4 h-4 flex-shrink-0" />
                    <span class="truncate">{{ initiatingArbitrationId === contract.id ? $t('contracts.arbitration.initiating') : $t('contracts.arbitration.initiate') }}</span>
                  </button>
                  <NuxtLink
                    v-if="contract.arbitration_room_id"
                    :to="localePath(`/chat?room_id=${contract.arbitration_room_id}`)"
                    class="btn-secondary btn-sm flex items-center justify-center gap-2 whitespace-nowrap"
                  >
                    <MessageCircle class="w-4 h-4 flex-shrink-0" />
                    <span class="truncate">{{ $t('contracts.arbitration.open_room') }}</span>
                  </NuxtLink>
                  <button
                    v-if="canCancel(contract)"
                    @click="promptCancelContract(contract)"
                    class="btn-outline-error btn-sm"
                  >
                    {{ getCancelButtonText(contract) }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <div v-else class="text-center py-12">
          <img src="/images/para/shrug.webp" alt="Para" class="mx-auto h-32 w-auto mb-4" />
          <h3 class="text-lg font-medium text-neutral-900 dark:text-neutral-100 mb-2">
            <template v-if="activeTab === 'pending'">{{ $t('contracts.empty.pending') }}</template>
            <template v-else-if="activeTab === 'signed'">{{ $t('contracts.empty.signed') }}</template>
            <template v-else>{{ $t('contracts.empty.completed') }}</template>
          </h3>
          <p class="text-neutral-500 dark:text-neutral-400 mb-6">
            {{ $t('contracts.empty.subtitle') }}
          </p>
          <UiButton variant="primary" size="sm" @click="openCreateModal">
            {{ $t('contracts.create_new') }}
          </UiButton>
        </div>
      </div>
      </UiTabs>

      <!-- Create Contract Modal -->
      <div v-if="showCreateModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="closeCreateModal">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto" @click.stop>
          <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">
            {{ $t('contracts.create.title') }}
          </h2>
          <form @submit.prevent="createContract" class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.create.title_label') }}
              </label>
              <input
                v-model="newContract.title"
                type="text"
                required
                :placeholder="$t('contracts.create.title_example')"
                class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"
              />
            </div>

            <div>
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.create.partner_label') }}
              </label>
              <!-- Empty partner guidance -->
              <div v-if="partners.length === 0 && temporaryPartners.length === 0" class="border border-dashed border-warning/50 rounded-lg p-3 bg-warning/5">
                <p class="text-sm text-neutral-600 dark:text-neutral-400">
                  {{ $t('contracts.create.no_partners_hint') }}
                </p>
                <NuxtLink :to="localePath('/directory')" class="text-link text-sm mt-1 inline-flex items-center gap-1">
                  {{ $t('contracts.create.find_people') }}
                  <ArrowRight class="w-3 h-3" />
                </NuxtLink>
              </div>
              <select
                v-else
                v-model="newContract.partner_id"
                required
                class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"
              >
                <option value="">{{ $t('contracts.create.select_partner') }}</option>

                <optgroup v-if="partners.length > 0" :label="$t('contracts.create.your_partners')">
                  <option v-for="partner in partners" :key="partner.id" :value="partner.id">
                    {{ partner.display_name || partner.hna }}
                  </option>
                </optgroup>

                <optgroup v-if="temporaryPartners.length > 0" :label="$t('contracts.create.other')">
                  <option v-for="partner in temporaryPartners" :key="partner.id" :value="partner.id">
                    {{ partner.display_name || partner.hna }}
                  </option>
                </optgroup>
              </select>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.create.arbiter_label') }}
              </label>
              <select
                v-model="newContract.arbiter_id"
                class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"
              >
                <option value="">{{ $t('contracts.create.no_arbiter') }}</option>
                <optgroup :label="$t('contracts.create.partners')">
                  <option
                    v-for="partner in availableArbiters"
                    :key="partner.id"
                    :value="partner.id"
                  >
                    {{ partner.display_name || partner.hna }}
                  </option>
                </optgroup>
              </select>
              <div class="flex gap-2 mt-1">
                <button type="button" @click="showArbiterBrowse = true" class="text-xs text-link">
                  {{ $t('contracts.create.browse_arbiters') }}
                </button>
                <button type="button" @click="showClauseGen = true" class="text-xs text-link">
                  {{ $t('contracts.create.generate_clause') }}
                </button>
              </div>
              <p class="text-xs text-neutral-500 mt-1">
                {{ $t('contracts.create.arbiter_hint') }}
              </p>
            </div>

            <!-- Items linkage -->
            <div v-if="myItems.length > 0 || partnerItems.length > 0">
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.create.items_label') }}
              </label>
              <div class="space-y-1 max-h-32 overflow-y-auto border rounded p-2 dark:border-neutral-600">
                <label
                  v-for="item in availableItems"
                  :key="item.id"
                  class="flex items-center gap-2 text-sm cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-700 rounded px-1"
                >
                  <input
                    type="checkbox"
                    :value="item.id"
                    v-model="newContract.item_ids"
                    class="rounded border-neutral-300 dark:border-neutral-600"
                  />
                  <span class="text-neutral-700 dark:text-neutral-300 truncate">{{ item.title }}</span>
                  <span class="text-xs text-neutral-400 ml-auto shrink-0">{{ item.owner_name }}</span>
                </label>
              </div>
              <p class="text-xs text-neutral-500 mt-1">
                {{ $t('contracts.create.items_hint') }}
              </p>
            </div>

            <!-- Contract content: Write or Upload toggle -->
            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.create.content_label') }}
              </label>
              <div class="flex gap-1 mb-3">
                <button
                  type="button"
                  @click="createMode = 'write'"
                  :class="[
                    'flex-1 px-3 py-1.5 text-sm rounded-l-lg border transition-colors',
                    createMode === 'write'
                      ? 'bg-primary/10 border-primary text-neutral-900 dark:text-neutral-100 font-medium'
                      : 'border-neutral-300 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'
                  ]"
                >
                  <Pencil class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                  {{ $t('contracts.create.mode_write') }}
                </button>
                <button
                  type="button"
                  @click="createMode = 'upload'"
                  :class="[
                    'flex-1 px-3 py-1.5 text-sm rounded-r-lg border transition-colors',
                    createMode === 'upload'
                      ? 'bg-primary/10 border-primary text-neutral-900 dark:text-neutral-100 font-medium'
                      : 'border-neutral-300 dark:border-neutral-600 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700'
                  ]"
                >
                  <Upload class="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                  {{ $t('contracts.create.mode_upload') }}
                </button>
              </div>

              <!-- Write mode: TipTap editor -->
              <div v-if="createMode === 'write'">
                <!-- Template quick-start -->
                <div class="flex flex-wrap gap-1.5 mb-2">
                  <button
                    v-for="tmpl in contractTemplates"
                    :key="tmpl.id"
                    type="button"
                    @click="applyTemplate(tmpl.id)"
                    class="px-2 py-1 text-xs rounded border border-neutral-200 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 hover:border-primary transition-colors"
                  >
                    {{ tmpl.label }}
                  </button>
                </div>
                <AdsRichEditor
                  v-model="contractTermsHtml"
                  :placeholder="$t('contracts.create.write_placeholder')"
                />
                <p class="text-xs text-neutral-500 mt-1">
                  {{ $t('contracts.create.write_hint') }}
                </p>
              </div>

              <!-- Upload mode: file upload -->
              <div v-if="createMode === 'upload'">
                <input
                  ref="fileInput"
                  type="file"
                  @change="handleFileSelect"
                  :disabled="isHashing"
                  class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100 disabled:opacity-50"
                />
                <p class="text-xs text-neutral-500 mt-1">
                  {{ $t('contracts.create.file_hint') }}
                </p>
              </div>
            </div>

            <!-- File info (upload mode) -->
            <div v-if="createMode === 'upload' && selectedFileName" class="text-sm text-neutral-600 dark:text-neutral-400">
              <div class="flex items-center justify-between">
                <span class="truncate">{{ selectedFileName }}</span>
                <span class="ml-2 text-xs">{{ formatFileSize(selectedFileSize) }}</span>
              </div>
            </div>

            <!-- Progress bar -->
            <div v-if="isHashing" class="space-y-2">
              <div class="flex items-center justify-between text-sm">
                <span class="text-neutral-600 dark:text-neutral-400">{{ $t('contracts.create.computing_hash') }}</span>
                <span class="font-medium text-primary">{{ hashProgress }}%</span>
              </div>
              <div class="w-full bg-neutral-200 dark:bg-neutral-700 rounded-full h-2 overflow-hidden">
                <div
                  class="bg-gradient-to-r from-primary to-secondary-400 h-full transition-all duration-300 ease-out"
                  :style="{ width: hashProgress + '%' }"
                ></div>
              </div>
            </div>

            <!-- SHA256 hash with animation -->
            <div
              v-if="newContract.file_sha256 && !isHashing"
              :class="[
                'p-3 rounded text-xs font-mono break-all transition-all duration-300',
                hashJustUpdated
                  ? 'bg-gradient-to-r from-green-100 to-secondary-100 dark:from-green-900/30 dark:to-secondary-900/30 ring-2 ring-primary shadow-lg scale-105'
                  : 'bg-neutral-100 dark:bg-neutral-700'
              ]"
            >
              <div class="flex items-start gap-2">
                <span class="text-neutral-500 dark:text-neutral-400 flex-shrink-0">SHA256:</span>
                <span class="text-neutral-900 dark:text-neutral-100">{{ newContract.file_sha256 }}</span>
              </div>
            </div>

            <div class="flex gap-2">
              <button
                type="submit"
                :disabled="creating || !newContract.file_sha256 || (!newContract.partner_id && partners.length === 0 && temporaryPartners.length === 0)"
                class="flex-1 px-4 py-2 bg-primary text-black font-medium rounded-lg hover:bg-opacity-90 disabled:opacity-50"
              >
                {{ creating ? $t('contracts.create.creating') : $t('contracts.create.submit') }}
              </button>
              <button
                type="button"
                @click="closeCreateModal"
                class="px-4 py-2 border rounded text-neutral-700 dark:text-neutral-300"
              >
                {{ $t('contracts.create.cancel') }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- Sign Contract Modal -->
      <div v-if="showSignModal && selectedContract" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="showSignModal = false">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-md w-full mx-4" @click.stop>
          <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">
            {{ $t('contracts.sign_modal.title') }}
          </h2>
          <div class="space-y-4">
            <div class="bg-neutral-100 dark:bg-neutral-700 p-3 rounded">
              <p class="font-semibold">{{ selectedContract.title }}</p>
              <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                {{ $t('contracts.sign_modal.from') }}: {{ selectedContract.creator_display_name }}
              </p>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2 font-mono break-all">
                SHA256: {{ selectedContract.file_sha256 }}
              </p>
            </div>

            <!-- Native contract: the actual terms, stored server-side (PRIVATE).
                 The partner reads them here, then signs. -->
            <div v-if="selectedContract.document_text" class="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
              <div class="px-3 py-2 border-b border-neutral-200 dark:border-neutral-700 text-xs uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                {{ $t('contracts.sign_modal.read_terms') }}
              </div>
              <div class="prose prose-sm dark:prose-invert max-w-none p-3 max-h-72 overflow-y-auto" v-html="selectedContract.document_text_html"></div>
            </div>

            <!-- File verification (legacy / upload contracts only — no stored body) -->
            <div v-if="!selectedContract.document_text" class="border-2 border-orange-300 dark:border-orange-700 rounded-lg p-4 bg-orange-50 dark:bg-orange-900/20">
              <p class="text-sm font-semibold text-orange-800 dark:text-orange-200 mb-2">
                {{ $t('contracts.sign_modal.verify_file') }}
              </p>
              <input
                ref="verifyFileInput"
                type="file"
                @change="handleVerifyFile"
                :disabled="verifyingHash"
                class="w-full px-3 py-2 border rounded text-sm dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100 disabled:opacity-50"
              />
              <p class="text-xs text-orange-700 dark:text-orange-300 mt-2">
                {{ $t('contracts.sign_modal.verify_hint') }}
              </p>

              <!-- Verification progress bar -->
              <div v-if="verifyingHash" class="mt-3 space-y-2">
                <div class="flex items-center justify-between text-sm">
                  <span class="text-orange-800 dark:text-orange-200">{{ $t('contracts.create.computing_hash') }}</span>
                  <span class="font-medium text-orange-900 dark:text-orange-100">{{ verifyHashProgress }}%</span>
                </div>
                <div class="w-full bg-orange-200 dark:bg-orange-800 rounded-full h-2 overflow-hidden">
                  <div
                    class="bg-gradient-to-r from-orange-500 to-red-500 h-full transition-all duration-300 ease-out"
                    :style="{ width: verifyHashProgress + '%' }"
                  ></div>
                </div>
              </div>
            </div>

            <!-- Hash verification status -->
            <div v-if="verifiedHash" :class="[
              'p-3 rounded-lg border-2',
              hashMatches
                ? 'bg-green-50 dark:bg-green-900/20 border-green-400 dark:border-green-600'
                : 'bg-red-50 dark:bg-red-900/20 border-red-400 dark:border-red-600'
            ]">
              <div class="flex items-center gap-2 mb-2">
                <span :class="hashMatches ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'" class="text-lg">
                  {{ hashMatches ? '✓' : '✗' }}
                </span>
                <span :class="hashMatches ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'" class="font-semibold text-sm">
                  {{ hashMatches ? $t('contracts.verify.match') : $t('contracts.verify.mismatch') }}
                </span>
              </div>
              <p class="text-xs font-mono break-all" :class="hashMatches ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
                {{ verifiedHash }}
              </p>
            </div>

            <UiAlert v-if="!hashMatches && verifiedHash" variant="error">
              {{ $t('contracts.sign_modal.hash_mismatch_warning') }}
            </UiAlert>

            <div class="flex gap-2">
              <button
                @click="signContract"
                :disabled="signing || !hashMatches"
                class="flex-1 btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ signing ? $t('contracts.sign_modal.signing') : $t('contracts.sign_modal.confirm') }}
              </button>
              <button
                @click="showSignModal = false"
                class="px-4 py-2 border rounded text-neutral-700 dark:text-neutral-300"
              >
                {{ $t('contracts.create.cancel') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Complete Contract Modal -->
      <div v-if="showCompleteModal && selectedContract" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="showCompleteModal = false">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-md w-full mx-4" @click.stop>
          <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">
            {{ $t('contracts.complete_modal.title') }}
          </h2>
          <form @submit.prevent="completeContract" class="space-y-4">
            <div class="bg-neutral-100 dark:bg-neutral-700 p-3 rounded">
              <p class="font-semibold">{{ selectedContract.title }}</p>
              <p class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                {{ getPartnerLabel(selectedContract) }}
              </p>
            </div>

            <div>
              <label class="block text-sm font-medium mb-2 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.complete_modal.rating_label') }}
              </label>
              <div class="flex gap-2">
                <button
                  v-for="star in 5"
                  :key="star"
                  type="button"
                  @click="reviewForm.rating = star"
                  class="text-2xl transition-colors"
                  :class="star <= reviewForm.rating ? 'text-yellow-400' : 'text-neutral-300 dark:text-neutral-600'"
                >
                  ★
                </button>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">
                {{ $t('contracts.complete_modal.review_label') }}
              </label>
              <textarea
                v-model="reviewForm.review_text"
                rows="4"
                :placeholder="$t('contracts.complete_modal.review_placeholder')"
                class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100"
              ></textarea>
            </div>

            <div class="flex gap-2">
              <button
                type="submit"
                :disabled="completing"
                class="flex-1 btn-success"
              >
                {{ completing ? $t('contracts.complete_modal.completing') : $t('contracts.complete_modal.submit') }}
              </button>
              <button
                type="button"
                @click="showCompleteModal = false"
                class="px-4 py-2 border rounded text-neutral-700 dark:text-neutral-300"
              >
                {{ $t('contracts.create.cancel') }}
              </button>
            </div>
          </form>
        </div>
      </div>
      <!-- Arbiter Browse Modal -->
      <div v-if="showArbiterBrowse" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="showArbiterBrowse = false">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto" @click.stop>
          <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">{{ $t('contracts.arbiter_profiles.title') }}</h2>
          <div v-if="arbiterProfiles.length === 0" class="text-center py-8 text-neutral-500 dark:text-neutral-400">
            {{ $t('contracts.arbiter_profiles.no_arbiters') }}
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="ap in arbiterProfiles"
              :key="ap.profile_id"
              class="border border-neutral-200 dark:border-neutral-700 rounded p-3 hover:bg-neutral-50 dark:hover:bg-neutral-700/50"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="flex-1">
                  <div class="font-medium text-neutral-900 dark:text-neutral-100">{{ ap.display_name }}</div>
                  <div class="text-xs text-neutral-500 dark:text-neutral-400">{{ ap.hna }}</div>
                  <p v-if="ap.bio" class="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{{ ap.bio }}</p>
                  <div class="flex flex-wrap gap-2 mt-2 text-xs">
                    <span v-if="ap.fee_amount" class="text-neutral-600 dark:text-neutral-400">
                      {{ $t('contracts.arbiter_profiles.fee') }}: {{ ap.fee_amount }} {{ ap.fee_currency }}
                    </span>
                    <span v-if="ap.avg_rating" class="text-amber-600 dark:text-amber-400">
                      {{ $t('contracts.arbiter_profiles.rating') }}: {{ ap.avg_rating }}/5 ({{ ap.total_cases }} {{ $t('contracts.arbiter_profiles.cases') }})
                    </span>
                  </div>
                  <div v-if="ap.specializations.length" class="flex flex-wrap gap-1 mt-1">
                    <span v-for="s in ap.specializations" :key="s.id" class="text-xs px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-700 rounded text-neutral-600 dark:text-neutral-400">
                      {{ s.name }}
                    </span>
                  </div>
                </div>
                <div class="flex flex-col gap-1.5 shrink-0">
                  <button @click="selectArbiter(ap)" class="btn-primary btn-xs">
                    {{ $t('contracts.arbiter_profiles.select') }}
                  </button>
                  <NuxtLink :to="localePath(`/arbiters/${ap.profile_id}`)" class="text-link text-xs text-center">
                    {{ $t('arbiter_stats.view_stats') }}
                  </NuxtLink>
                </div>
              </div>
            </div>
          </div>
          <button @click="showArbiterBrowse = false" class="mt-4 w-full px-4 py-2 border rounded text-neutral-700 dark:text-neutral-300">
            {{ $t('contracts.create.cancel') }}
          </button>
        </div>
      </div>

      <!-- Clause Generation Modal -->
      <div v-if="showClauseGen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click="showClauseGen = false">
        <div class="bg-white dark:bg-neutral-800 rounded-lg p-6 max-w-lg w-full mx-4" @click.stop>
          <h2 class="text-xl font-bold mb-4 text-neutral-900 dark:text-neutral-100">{{ $t('contracts.clause.title') }}</h2>
          <div class="space-y-3">
            <div>
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.clause.type_label') }}</label>
              <select v-model="clauseForm.type" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100">
                <option value="ad_hoc">{{ $t('contracts.clause.ad_hoc') }}</option>
                <option value="institutional">{{ $t('contracts.clause.institutional') }}</option>
                <option value="escalated">{{ $t('contracts.clause.escalated') }}</option>
              </select>
            </div>
            <div v-if="clauseForm.type !== 'institutional'">
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.clause.arbiter_name_label') }}</label>
              <input v-model="clauseForm.arbiter_name" type="text" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100" />
            </div>
            <div v-if="clauseForm.type !== 'institutional'">
              <label class="block text-sm font-medium mb-1 text-neutral-700 dark:text-neutral-300">{{ $t('contracts.clause.city_label') }}</label>
              <input v-model="clauseForm.city" type="text" class="w-full px-3 py-2 border rounded dark:bg-neutral-700 dark:border-neutral-600 text-neutral-900 dark:text-neutral-100" />
            </div>
            <button @click="generateClause" :disabled="generatingClause" class="btn-primary btn-sm w-full">
              {{ $t('contracts.clause.generate') }}
            </button>
            <div v-if="generatedClause" class="bg-neutral-100 dark:bg-neutral-700 rounded p-3 text-sm text-neutral-800 dark:text-neutral-200 whitespace-pre-wrap">
              {{ generatedClause }}
            </div>
            <div v-if="generatedClause" class="flex gap-2">
              <button @click="copyClause" class="btn-outline btn-sm flex-1">{{ $t('contracts.clause.copy') }}</button>
            </div>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('contracts.clause.legal_note') }}</p>
          </div>
          <button @click="showClauseGen = false" class="mt-4 w-full px-4 py-2 border rounded text-neutral-700 dark:text-neutral-300">
            {{ $t('contracts.create.cancel') }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <UiConfirmModal
    v-model="showCancelContractConfirm"
    :title="$t(`contracts.confirm.${pendingCancelAction || 'cancel'}`)"
    :message="$t(`contracts.confirm.${pendingCancelAction || 'cancel'}`)"
    :icon="XCircle"
    variant="error"
    :confirm-label="$t(`contracts.confirm.${pendingCancelAction || 'cancel'}`)"
    @confirm="cancelContract(pendingCancelContract)"
  />

  <UiConfirmModal
    v-model="showArbitrationConfirm"
    :title="$t('contracts.arbitration.confirm_initiate')"
    :message="$t('contracts.arbitration.confirm_initiate')"
    :icon="Scale"
    variant="warning"
    :confirm-label="$t('contracts.arbitration.initiate')"
    @confirm="initiateArbitration(pendingArbitrationContract)"
  />

  <UiConfirmModal
    v-model="showEscalateConfirm"
    :title="$t('contracts.confirm.escalate')"
    :message="$t('contracts.confirm.escalate')"
    :icon="AlertTriangle"
    variant="warning"
    :confirm-label="$t('contracts.confirm.escalate')"
    @confirm="escalateArbitration(pendingEscalateContractId)"
  />
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Plus, FileText, Download, Scale, ChevronDown, ArrowRight, Pencil, Upload, MessageCircle, XCircle, AlertTriangle } from 'lucide-vue-next'
import AdsRichEditor from '~/components/Ads/RichEditor.vue'
import { useAuthStore } from '~/stores/auth'
import { useToastStore } from '~/stores/toast'
import { useWebSocket } from '~/composables/useWebSocket'
import { usePGP } from '~/composables/usePGP'

const authStore = useAuthStore()
const toastStore = useToastStore()
const { t: $t } = useI18n()
const { computeFileSHA256, signMessage, hasKeys, loadKeys } = usePGP()

useSeoMeta({
  title: $t('contracts.title') + ' - Parahub',
  ogTitle: $t('contracts.title') + ' - Parahub',
})

definePageMeta({
  middleware: 'auth',
  keepalive: true
})

const contracts = ref([])
const partners = ref([])
const temporaryPartners = ref([])
const loading = ref(false)
const creating = ref(false)
const signing = ref(false)
const activeTab = useTabSync(['pending', 'signed', 'completed'])
const showCreateModal = ref(false)
const showSignModal = ref(false)
const showCompleteModal = ref(false)
const selectedContract = ref(null)
const fileInput = ref(null)
const verifyFileInput = ref(null)
const completing = ref(false)
const verifyingHash = ref(false)
const verifyHashProgress = ref(0)
const verifiedHash = ref('')
const hashMatches = ref(false)
const exportingContractId = ref(null)
const initiatingArbitrationId = ref(null)
const submittingVerdictId = ref(null)
const ratingArbiterId = ref(null)
const escalatingId = ref(null)
const showCancelContractConfirm = ref(false)
const pendingCancelContract = ref(null)
const pendingCancelAction = ref('')
const showArbitrationConfirm = ref(false)
const pendingArbitrationContract = ref(null)
const showEscalateConfirm = ref(false)
const pendingEscalateContractId = ref(null)

// Arbiter browse
const showArbiterBrowse = ref(false)
const arbiterProfiles = ref([])

// Clause generation
const showClauseGen = ref(false)
const clauseForm = ref({ type: 'ad_hoc', arbiter_name: '', city: 'Lisboa' })
const generatedClause = ref('')
const generatingClause = ref(false)

const myItems = ref([])
const partnerItems = ref([])

const newContract = ref({
  title: '',
  partner_id: '',
  arbiter_id: '',
  file_sha256: '',
  file: null,
  item_ids: [],
  kind: 'SALE',        // 'SALE' (default) | 'RENTAL' (set by the formalize-rental flow)
  booking_id: null     // rental.Booking to link when formalizing a confirmed booking
})

const hashProgress = ref(0)
const isHashing = ref(false)
const selectedFileName = ref('')
const selectedFileSize = ref(0)
const hashJustUpdated = ref(false)

// Collapsible cards
const expandedContracts = ref(new Set())

// Create mode: 'write' (TipTap) or 'upload' (file)
const createMode = ref('write')
const contractTermsHtml = ref('')

const reviewForm = ref({
  rating: 5,
  review_text: ''
})

const { locale } = useI18n()

function toggleExpand(contractId) {
  if (expandedContracts.value.has(contractId)) {
    expandedContracts.value.delete(contractId)
  } else {
    expandedContracts.value.add(contractId)
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString(locale.value, {
    year: 'numeric', month: 'short', day: 'numeric'
  })
}

const contractTemplates = computed(() => [
  { id: 'service', label: $t('contracts.templates.service') },
  { id: 'sale', label: $t('contracts.templates.sale') },
  { id: 'rental', label: $t('contracts.templates.rental') },
  { id: 'loan', label: $t('contracts.templates.loan') },
])

function applyTemplate(templateId, fill = {}) {
  const templates = {
    service: $t('contracts.templates.service_body'),
    sale: $t('contracts.templates.sale_body'),
    rental: $t('contracts.templates.rental_body'),
    loan: $t('contracts.templates.loan_body'),
  }
  let body = templates[templateId] || ''
  // [[token]] placeholders are filled from the booking/item when formalizing a
  // booking; anything not provided becomes a fill-in-the-blank line for manual
  // entry (so the plain template buttons still produce a usable draft).
  // NB: [[ ]] (not { }) because vue-i18n parses braces as interpolation.
  body = body.replace(/\[\[(\w+)\]\]/g, (_, key) => {
    const v = fill[key]
    return (v !== undefined && v !== null && v !== '') ? String(v) : '__________'
  })
  contractTermsHtml.value = body
}

// When contractTermsHtml changes (write mode), compute SHA256 from text content
let termsHashTimeout = null
watch(contractTermsHtml, (html) => {
  if (createMode.value !== 'write' || !html) {
    if (createMode.value === 'write') {
      newContract.value.file_sha256 = ''
    }
    return
  }
  // Debounce — hash after 500ms of no typing
  clearTimeout(termsHashTimeout)
  termsHashTimeout = setTimeout(async () => {
    try {
      // Strip HTML to get plain text for hashing
      const plainText = html.replace(/<[^>]*>/g, '').trim()
      if (!plainText) {
        newContract.value.file_sha256 = ''
        return
      }
      isHashing.value = true
      hashProgress.value = 0
      const blob = new Blob([html], { type: 'text/html' })
      const sha256 = await computeFileSHA256(blob, (p) => { hashProgress.value = p })
      newContract.value.file_sha256 = sha256
      isHashing.value = false
      hashJustUpdated.value = true
      setTimeout(() => { hashJustUpdated.value = false }, 600)
    } catch (e) {
      isHashing.value = false
      console.error('Failed to hash terms:', e)
    }
  }, 500)
})

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const filteredContracts = computed(() => {
  if (!contracts.value) return []

  if (activeTab.value === 'pending') {
    return contracts.value.filter(c => c.status === 'PENDING_PARTNER')
  } else if (activeTab.value === 'signed') {
    return contracts.value.filter(c => c.status === 'SIGNED')
  } else {
    return contracts.value.filter(c => c.status === 'COMPLETED')
  }
})

const pendingCount = computed(() => {
  if (!contracts.value) return 0
  return contracts.value.filter(c => c.status === 'PENDING_PARTNER').length
})

const signedCount = computed(() => {
  if (!contracts.value) return 0
  return contracts.value.filter(c => c.status === 'SIGNED').length
})

const completedCount = computed(() => {
  if (!contracts.value) return 0
  return contracts.value.filter(c => c.status === 'COMPLETED').length
})

const contractTabs = computed(() => [
  { id: 'pending', label: $t('contracts.tabs.pending'), badge: pendingCount.value > 0 ? pendingCount.value : undefined },
  { id: 'signed', label: $t('contracts.tabs.signed'), badge: signedCount.value > 0 ? signedCount.value : undefined },
  { id: 'completed', label: $t('contracts.tabs.completed'), badge: completedCount.value > 0 ? completedCount.value : undefined },
])

const availableArbiters = computed(() => {
  // Filter out selected partner from arbiter list
  return partners.value.filter(p => p.id !== newContract.value.partner_id)
})

const availableItems = computed(() => {
  const me = authStore.activeProfile
  return [
    ...myItems.value.map(i => ({ ...i, owner_name: me?.display_name || me?.hna || '' })),
    ...partnerItems.value.map(i => ({ ...i, owner_name: i._partner_name || '' }))
  ]
})

const canSign = (contract) => {
  const myId = authStore.activeProfile?.id
  return contract.partner_id === myId && !contract.partner_signed_at
}

const canComplete = (contract) => {
  const myId = authStore.activeProfile?.id
  if (!myId) return false

  // Must be signed or partially completed
  if (contract.status !== 'SIGNED' && contract.status !== 'COMPLETED') return false

  // Check if I haven't completed yet
  const isCreator = contract.creator_id === myId
  const isPartner = contract.partner_id === myId

  if (isCreator) {
    return !contract.creator_completed_at
  } else if (isPartner) {
    return !contract.partner_completed_at
  }

  return false
}

const canCancel = (contract) => {
  const myId = authStore.activeProfile?.id
  return contract.status === 'PENDING_PARTNER' && (contract.creator_id === myId || contract.partner_id === myId)
}

const canInitiateArbitration = (contract) => {
  const myId = authStore.activeProfile?.id
  if (!myId) return false

  // Must be SIGNED (active contract)
  if (contract.status !== 'SIGNED') return false

  // Must have arbiter
  if (!contract.arbiter_id) return false

  // Must be creator or partner
  if (contract.creator_id !== myId && contract.partner_id !== myId) return false

  // Not yet initiated
  return !contract.arbitration_room_id
}

const getCancelButtonText = (contract) => {
  const myId = authStore.activeProfile?.id
  return contract.creator_id === myId ? $t('contracts.cancel_contract') : $t('contracts.reject_contract')
}

const getPartnerLabel = (contract) => {
  const myId = authStore.activeProfile?.id
  if (contract.creator_id === myId) {
    return $t('contracts.with') + ': ' + contract.partner_display_name
  } else {
    return $t('contracts.from') + ': ' + contract.creator_display_name
  }
}

// Fetch items when partner changes
watch(() => newContract.value.partner_id, async (partnerId) => {
  partnerItems.value = []
  newContract.value.item_ids = []
  if (!partnerId) return
  try {
    await authStore.ensureToken()
    const res = await $fetch(`/api/v1/items/?owner_id=${partnerId}&is_active=true`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    const items = res.items || res || []
    const partner = partners.value.find(p => p.id === partnerId) || temporaryPartners.value.find(p => p.id === partnerId)
    partnerItems.value = items.map(i => ({ ...i, _partner_name: partner?.display_name || partner?.hna || '' }))
  } catch (e) {
    console.error('Failed to fetch partner items:', e)
  }
})

async function fetchMyItems() {
  try {
    await authStore.ensureToken()
    const res = await $fetch(`/api/v1/items/?owner_id=${authStore.activeProfile.id}&is_active=true`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    myItems.value = res.items || res || []
  } catch (e) {
    console.error('Failed to fetch my items:', e)
  }
}

function openCreateModal() {
  newContract.value.title = ''
  // Generic create — clear any rental context a prior formalize may have left.
  newContract.value.kind = 'SALE'
  newContract.value.booking_id = null
  createMode.value = 'write'
  contractTermsHtml.value = ''
  fetchMyItems()
  showCreateModal.value = true
}

function closeCreateModal() {
  showCreateModal.value = false
  // Reset form
  newContract.value = {
    title: '',
    partner_id: '',
    arbiter_id: '',
    file_sha256: '',
    file: null,
    item_ids: [],
    kind: 'SALE',
    booking_id: null
  }
  myItems.value = []
  partnerItems.value = []
  // Reset progress states
  hashProgress.value = 0
  isHashing.value = false
  selectedFileName.value = ''
  selectedFileSize.value = 0
  hashJustUpdated.value = false
  createMode.value = 'write'
  contractTermsHtml.value = ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

async function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (!file) return

  try {
    isHashing.value = true
    hashProgress.value = 0
    selectedFileName.value = file.name
    selectedFileSize.value = file.size

    const sha256 = await computeFileSHA256(file, (progress) => {
      hashProgress.value = progress
    })

    newContract.value.file_sha256 = sha256
    newContract.value.file = file
    isHashing.value = false

    // Trigger animation
    hashJustUpdated.value = true
    setTimeout(() => {
      hashJustUpdated.value = false
    }, 600)
  } catch (error) {
    isHashing.value = false
    toastStore.error($t('contracts.errors.file_hash_failed'))
    console.error('Failed to compute file hash:', error)
  }
}

async function createContract() {
  if (!hasKeys.value) {
    toastStore.error($t('contracts.errors.no_pgp_keys'))
    return
  }

  creating.value = true
  try {
    await authStore.ensureToken()

    // Create canonical JSON for signing (WITHOUT created_at - will be added by server)
    const canonicalPayload = {
      title: newContract.value.title,
      creator_id: authStore.activeProfile.id,
      partner_id: newContract.value.partner_id,
      file_sha256: newContract.value.file_sha256
    }

    // Include arbiter if specified
    if (newContract.value.arbiter_id) {
      canonicalPayload.arbiter_id = newContract.value.arbiter_id
    }

    // IMPORTANT: Must match Python's json.dumps(sort_keys=True, separators=(',', ':'))
    const sortedKeys = Object.keys(canonicalPayload).sort()
    const sortedPayload = {}
    for (const key of sortedKeys) {
      sortedPayload[key] = canonicalPayload[key]
    }
    const canonicalData = JSON.stringify(sortedPayload)

    // Sign with PGP (signature will be verified on server with same payload)
    const signature = await signMessage(canonicalData)

    // Create contract
    const response = await $fetch('/api/v1/contracts/', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        partner_id: newContract.value.partner_id,
        title: newContract.value.title,
        file_sha256: newContract.value.file_sha256,
        arbiter_id: newContract.value.arbiter_id || null,
        signature: signature,
        item_ids: newContract.value.item_ids.length > 0 ? newContract.value.item_ids : null,
        kind: newContract.value.kind || 'SALE',
        // Store the composed body server-side (PRIVATE) so the counterparty can
        // read the actual terms in-app before signing. Upload mode keeps it null
        // (legacy hash-only). The hash already proves this exact text.
        document_text: createMode.value === 'write' ? contractTermsHtml.value : null,
        document_format: 'html',
        booking_id: newContract.value.booking_id || null
      }
    })

    // If written inline, offer download of the contract file for records
    if (createMode.value === 'write' && contractTermsHtml.value) {
      const blob = new Blob([contractTermsHtml.value], { type: 'text/html' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${newContract.value.title || 'contract'}.html`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }

    toastStore.success($t('contracts.success.created'))
    closeCreateModal()
    await fetchContracts()
  } catch (error) {
    console.error('Failed to create contract:', error)
    toastStore.error(error.data?.detail || $t('contracts.errors.create_failed'))
  } finally {
    creating.value = false
  }
}

async function openSignModal(contract) {
  selectedContract.value = contract
  verifiedHash.value = ''
  hashMatches.value = false
  verifyHashProgress.value = 0
  verifyingHash.value = false
  showSignModal.value = true
  // Native contract: the body is stored server-side. Confirm the rendered text
  // hashes to the signed file_sha256 (cryptographic WYSIWYG) so the partner can
  // read-and-sign without re-uploading a file. Legacy/upload contracts keep the
  // manual file-verify path (handleVerifyFile).
  if (contract.document_text) {
    try {
      const blob = new Blob([contract.document_text], { type: 'text/html' })
      const sha256 = await computeFileSHA256(blob)
      verifiedHash.value = sha256
      hashMatches.value = sha256 === contract.file_sha256
    } catch (e) {
      console.error('Failed to verify stored document hash:', e)
    }
  }
}

async function handleVerifyFile(event) {
  const file = event.target.files?.[0]
  if (!file) return

  try {
    verifyingHash.value = true
    verifyHashProgress.value = 0

    const sha256 = await computeFileSHA256(file, (progress) => {
      verifyHashProgress.value = progress
    })

    verifiedHash.value = sha256

    // Compare with contract hash
    hashMatches.value = sha256 === selectedContract.value.file_sha256

    if (hashMatches.value) {
      toastStore.success($t('contracts.verify.match'))
    } else {
      toastStore.error($t('contracts.verify.mismatch'))
    }
  } catch (error) {
    toastStore.error($t('contracts.errors.file_hash_failed'))
    console.error('Failed to verify file hash:', error)
  } finally {
    verifyingHash.value = false
  }
}

function openCompleteModal(contract) {
  selectedContract.value = contract
  reviewForm.value = {
    rating: 5,
    review_text: ''
  }
  showCompleteModal.value = true
}

async function signContract() {
  if (!hasKeys.value) {
    toastStore.error($t('contracts.errors.no_pgp_keys'))
    return
  }

  signing.value = true
  try {
    await authStore.ensureToken()

    // Create canonical JSON (same as creator - WITHOUT created_at)
    const canonicalPayload = {
      title: selectedContract.value.title,
      creator_id: selectedContract.value.creator_id,
      partner_id: selectedContract.value.partner_id,
      file_sha256: selectedContract.value.file_sha256
    }

    // Include arbiter if specified
    if (selectedContract.value.arbiter_id) {
      canonicalPayload.arbiter_id = selectedContract.value.arbiter_id
    }

    // IMPORTANT: Must match Python's json.dumps(sort_keys=True, separators=(',', ':'))
    const sortedKeys = Object.keys(canonicalPayload).sort()
    const sortedPayload = {}
    for (const key of sortedKeys) {
      sortedPayload[key] = canonicalPayload[key]
    }
    const canonicalData = JSON.stringify(sortedPayload)

    // Sign with PGP
    const signature = await signMessage(canonicalData)

    // Submit signature
    await $fetch(`/api/v1/contracts/${selectedContract.value.id}/sign/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        signature: signature
      }
    })

    toastStore.success($t('contracts.success.signed'))
    showSignModal.value = false
    selectedContract.value = null
    await fetchContracts()
  } catch (error) {
    console.error('Failed to sign contract:', error)
    toastStore.error(error.data?.detail || $t('contracts.errors.sign_failed'))
  } finally {
    signing.value = false
  }
}

function promptCancelContract(contract) {
  const myId = authStore.activeProfile?.id
  const isCreator = contract.creator_id === myId
  pendingCancelAction.value = isCreator ? 'cancel' : 'reject'
  pendingCancelContract.value = contract
  showCancelContractConfirm.value = true
}

async function cancelContract(contract) {
  showCancelContractConfirm.value = false
  const myId = authStore.activeProfile?.id
  const isCreator = contract.creator_id === myId
  const action = isCreator ? 'cancel' : 'reject'

  try {
    await authStore.ensureToken()

    await $fetch(`/api/v1/contracts/${contract.id}/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    toastStore.success($t(`contracts.success.${action}ed`))
    await fetchContracts()
  } catch (error) {
    console.error(`Failed to ${action} contract:`, error)
    toastStore.error(error.data?.detail || $t('contracts.errors.cancel_failed'))
  }
}

async function completeContract() {
  completing.value = true
  try {
    await authStore.ensureToken()

    await $fetch(`/api/v1/contracts/${selectedContract.value.id}/complete/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      },
      body: {
        rating: reviewForm.value.rating,
        review_text: reviewForm.value.review_text || null
      }
    })

    toastStore.success($t('contracts.success.completed'))
    showCompleteModal.value = false
    selectedContract.value = null
    reviewForm.value = { rating: 5, review_text: '' }
    await fetchContracts()
  } catch (error) {
    console.error('Failed to complete contract:', error)
    toastStore.error(error.data?.detail || $t('contracts.errors.complete_failed'))
  } finally {
    completing.value = false
  }
}

function promptArbitration(contract) {
  pendingArbitrationContract.value = contract
  showArbitrationConfirm.value = true
}

async function initiateArbitration(contract) {
  showArbitrationConfirm.value = false
  initiatingArbitrationId.value = contract.id
  try {
    await authStore.ensureToken()

    const response = await $fetch(`/api/v1/contracts/${contract.id}/initiate_arbitration/`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    // Update local contract with arbitration info
    const contractIndex = contracts.value.findIndex(c => c.id === contract.id)
    if (contractIndex !== -1) {
      contracts.value[contractIndex] = response
    }

    toastStore.success($t('contracts.arbitration.initiated'))

    // Navigate to chat page, then to specific room
    // (Element needs time to SSO login first)
    if (response.arbitration_room_id) {
      const roomId = response.arbitration_room_id

      // First go to chat page (Element will auto-login via SSO)
      await navigateTo(localePath('/chat'))

      // Wait 3 seconds for Element SSO login, then navigate to room
      setTimeout(() => {
        navigateTo(localePath(`/chat?room_id=${roomId}`))
      }, 3000)
    }
  } catch (error) {
    console.error('Failed to initiate arbitration:', error)
    toastStore.error(error.data?.detail || $t('contracts.arbitration.initiate_failed'))
  } finally {
    initiatingArbitrationId.value = null
  }
}

async function submitVerdict(data) {
  submittingVerdictId.value = data.contractId
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/contracts/${data.contractId}/verdict/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: {
        verdict_type: data.verdict_type,
        summary: data.summary,
        amount_awarded: data.amount_awarded || null,
        currency: data.currency || null,
      }
    })
    toastStore.success($t('contracts.success.verdict_submitted'))
    await fetchContracts()
  } catch (error) {
    console.error('Failed to submit verdict:', error)
    toastStore.error(error.data?.detail || $t('contracts.errors.verdict_failed'))
  } finally {
    submittingVerdictId.value = null
  }
}

async function rateArbiter(data) {
  ratingArbiterId.value = data.contractId
  try {
    await authStore.ensureToken()
    await $fetch(`/api/v1/contracts/${data.contractId}/rate-arbiter/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: { rating: data.rating }
    })
    toastStore.success($t('contracts.success.arbiter_rated'))
    await fetchContracts()
  } catch (error) {
    console.error('Failed to rate arbiter:', error)
    toastStore.error(error.data?.detail || $t('contracts.errors.rate_failed'))
  } finally {
    ratingArbiterId.value = null
  }
}

function promptEscalate(contractId) {
  pendingEscalateContractId.value = contractId
  showEscalateConfirm.value = true
}

async function escalateArbitration(contractId) {
  showEscalateConfirm.value = false
  escalatingId.value = contractId
  try {
    await authStore.ensureToken()
    const response = await $fetch(`/api/v1/contracts/${contractId}/escalate/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    const idx = contracts.value.findIndex(c => c.id === contractId)
    if (idx !== -1) contracts.value[idx] = response
    toastStore.success($t('contracts.success.escalated'))
  } catch (error) {
    console.error('Failed to escalate:', error)
    toastStore.error(error.data?.detail || $t('contracts.errors.escalate_failed'))
  } finally {
    escalatingId.value = null
  }
}

async function fetchArbiterProfiles() {
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/contracts/arbiter-profiles/', {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    arbiterProfiles.value = response || []
  } catch (error) {
    console.error('Failed to fetch arbiter profiles:', error)
  }
}

function selectArbiter(ap) {
  // Add to partners temporarily if not there
  const isInPartners = partners.value.some(p => p.id === ap.profile_id)
  if (!isInPartners) {
    const isInTemp = temporaryPartners.value.some(p => p.id === ap.profile_id)
    if (!isInTemp) {
      temporaryPartners.value.push({
        id: ap.profile_id,
        hna: ap.hna,
        display_name: ap.display_name,
        _temporary: true
      })
    }
  }
  newContract.value.arbiter_id = ap.profile_id
  showArbiterBrowse.value = false
}

async function generateClause() {
  generatingClause.value = true
  try {
    await authStore.ensureToken()
    const params = new URLSearchParams({
      type: clauseForm.value.type,
      city: clauseForm.value.city || 'Lisboa',
      arbiter_name: clauseForm.value.arbiter_name || '',
      lang: authStore.activeProfile?.preferred_language || 'pt',
    })
    const response = await $fetch(`/api/v1/contracts/clause-template/?${params}`, {
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    generatedClause.value = response.text
  } catch (error) {
    console.error('Failed to generate clause:', error)
    toastStore.error($t('contracts.errors.clause_failed'))
  } finally {
    generatingClause.value = false
  }
}

async function copyClause() {
  try {
    await navigator.clipboard.writeText(generatedClause.value)
    toastStore.success($t('contracts.success.clause_copied'))
  } catch {
    // Fallback
    const ta = document.createElement('textarea')
    ta.value = generatedClause.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    toastStore.success($t('contracts.success.clause_copied'))
  }
}

// Watch for arbiter browse modal open to fetch data
watch(showArbiterBrowse, (val) => {
  if (val && arbiterProfiles.value.length === 0) fetchArbiterProfiles()
})

async function fetchContracts() {
  loading.value = true
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/contracts/', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    contracts.value = response || []
  } catch (error) {
    console.error('Failed to fetch contracts:', error)
    toastStore.error($t('contracts.errors.fetch_failed'))
  } finally {
    loading.value = false
  }
}

async function fetchPartners() {
  try {
    await authStore.ensureToken()
    const response = await $fetch('/api/v1/partners/list/', {
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    // Handle paginated response
    partners.value = response.items || response || []
  } catch (error) {
    console.error('Failed to fetch partners:', error)
  }
}

// WebSocket for real-time updates
const { connect: connectWS, disconnect: disconnectWS } = useWebSocket({
  path: '/ws/v1/realtime/',
  onMessage: (data) => {
    if (data.type === 'contract.created' || data.type === 'contract.updated') {
      handleContractUpdate(data.contract)
    }
  },
  onOpen: () => {},
  autoReconnect: true
})

function handleContractUpdate(contractData) {
  if (!contractData) return

  const myId = authStore.activeProfile?.id
  const index = contracts.value.findIndex(c => c.id === contractData.id)

  if (index === -1) {
    // New contract
    contracts.value.unshift(contractData)

    // Show toast if I'm partner (received contract)
    if (contractData.partner_id === myId) {
      toastStore.info($t('contracts.toast.new_contract', { creator: contractData.creator_display_name }))
    }
  } else {
    // Update existing contract
    const oldContract = contracts.value[index]

    // Show toast if contract signed
    if (oldContract.status !== contractData.status && contractData.status === 'SIGNED') {
      if (contractData.creator_id === myId) {
        toastStore.success($t('contracts.toast.partner_signed', { partner: contractData.partner_display_name }))
      }
    }

    contracts.value[index] = contractData
  }
}

async function exportProof(contractId) {
  try {
    exportingContractId.value = contractId

    const response = await $fetch(`/api/v1/audit/export/contract/${contractId}`, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      },
      responseType: 'blob'
    })

    // Create download link
    const url = window.URL.createObjectURL(response)
    const a = document.createElement('a')
    a.href = url
    a.download = `contract_${contractId}_proof.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)

    toastStore.success($t('contracts.toast.proof_exported'))
  } catch (error) {
    console.error('Failed to export proof:', error)
    toastStore.error($t('contracts.toast.proof_export_failed'))
  } finally {
    exportingContractId.value = null
  }
}

const route = useRoute()
const router = useRouter()
const localePath = useLocalePath()

async function handleQueryParams() {
  if (!route.query.partner) return
  const partnerId = String(route.query.partner)
  const itemId = route.query.item ? String(route.query.item) : null
  const kind = route.query.kind ? String(route.query.kind) : null
  const bookingId = route.query.booking ? String(route.query.booking) : null

  try {
    await authStore.ensureToken()
    const partnerProfile = await $fetch(`/api/v1/profiles/${partnerId}/`, {
      credentials: 'include',
      headers: authStore.token ? {
        'Authorization': `Bearer ${authStore.token}`
      } : {}
    })

    const isInPartners = partners.value.some(p => p.id === partnerId)

    if (!isInPartners) {
      temporaryPartners.value = [{
        id: partnerProfile.id,
        hna: partnerProfile.hna,
        display_name: partnerProfile.display_name,
        _temporary: true
      }]
    }

    newContract.value.partner_id = partnerId

    // If item param present — fetch item and pre-fill
    let itemOwnerId = null
    if (itemId) {
      try {
        const itemData = await $fetch(`/api/v1/items/${itemId}/`, {
          credentials: 'include',
          headers: authStore.token ? {
            'Authorization': `Bearer ${authStore.token}`
          } : {}
        })
        // Auto-fill title from item
        newContract.value.title = itemData.title
        itemOwnerId = itemData.owner_id || null
        // Pre-select item in the items list
        await fetchMyItems()
        // Add partner items manually (watcher won't fire since partner_id was set above)
        const partnerName = partnerProfile.display_name || partnerProfile.hna || ''
        partnerItems.value = [{ id: itemData.id, title: itemData.title, type: itemData.item_type, _partner_name: partnerName }]
        newContract.value.item_ids = [itemData.id]
      } catch (e) {
        console.error('Failed to load item from query:', e)
      }
    }

    // Formalize-rental flow: ?kind=rental[&booking=<id>] → write mode, RENTAL,
    // rental template prefilled from the booking + item (the counterparty then
    // reads the rendered terms in the sign modal and signs).
    if (kind === 'rental') {
      newContract.value.kind = 'RENTAL'
      newContract.value.booking_id = bookingId
      createMode.value = 'write'
      const fmtD = (s) => s ? new Date(s).toLocaleDateString(locale.value, { year: 'numeric', month: 'short', day: 'numeric' }) : ''
      const fmtM = (a, c) => (a !== null && a !== undefined && a !== '') ? `${a} ${c || ''}`.trim() : ''
      // Owner vs renter is decided by who actually owns the item, not by who
      // created the contract — so the template reads correctly whether the owner
      // formalizes from their inbox or the renter proposes from the item page.
      const me = authStore.activeProfile
      const meName = me?.display_name || me?.hna || ''
      const partnerName = partnerProfile.display_name || partnerProfile.hna || ''
      const iAmOwner = itemOwnerId ? me?.id === itemOwnerId : true
      const fill = {
        owner: iAmOwner ? meName : partnerName,
        renter: iAmOwner ? partnerName : meName,
        item: newContract.value.title || '',
      }
      if (bookingId) {
        try {
          const bk = await $fetch(`/api/v1/rental/bookings/${bookingId}`, {
            credentials: 'include',
            headers: authStore.token ? { 'Authorization': `Bearer ${authStore.token}` } : {}
          })
          fill.period = `${fmtD(bk.start)} — ${fmtD(bk.end)}`.trim()
          fill.rent = fmtM(bk.price_total, bk.currency)
          fill.deposit = fmtM(bk.deposit_amount, bk.currency)
          if (!fill.item && bk.item_title) {
            newContract.value.title = bk.item_title
            fill.item = bk.item_title
          }
        } catch (e) {
          console.error('Failed to load booking for formalize:', e)
        }
      }
      if (newContract.value.title) {
        newContract.value.title = $t('contracts.rental_title', { item: newContract.value.title })
      }
      applyTemplate('rental', fill)
    }

    showCreateModal.value = true
    router.replace({ query: {} })
  } catch (error) {
    console.error('Failed to load partner from query:', error)
    toastStore.error($t('contracts.toast.partner_load_failed'))
  }
}

// Handle query params on route change (keepalive re-activation)
watch(() => route.query.partner, (val) => {
  if (val) handleQueryParams()
})

onMounted(async () => {
  connectWS()
  await handleQueryParams()
})

onUnmounted(() => {
  disconnectWS()
})

// Client-side fetch behind Suspense (token-authed → no SSR): client-side
// navigation holds the previous page until keys/contracts/partners are ready
// instead of flashing an empty shell (was inside onMounted; onMounted runs
// after this resolves, so connectWS/handleQueryParams still see loaded data).
const bootstrap = useAsyncData('contracts-bootstrap', async () => {
  await loadKeys()
  await fetchContracts()
  await fetchPartners()
  return true
}, { server: false })

await bootstrap
</script>
