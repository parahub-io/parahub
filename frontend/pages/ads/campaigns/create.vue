<template>
  <div class="w-full max-w-5xl mx-auto">
    <!-- Header -->
    <div class="mb-6 flex items-center gap-3">
      <button
        @click="navigateTo(localePath('/ads/campaigns'))"
        class="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-600 dark:text-neutral-400"
      >
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h2 class="text-xl font-semibold text-neutral-900 dark:text-neutral-100">{{ $t('ads.create_campaign.title') }}</h2>
    </div>

    <!-- Wallet status banner -->
    <UiAlert v-if="profileLoaded && advertiserWalletConfigured" variant="success" :title="$t('ads.create_campaign.wallet_ready')" class="mb-6">
      {{ walletProvider }} &middot; {{ $t('ads.create_campaign.wallet_ready_desc') }}
    </UiAlert>
    <UiAlert v-else-if="profileLoaded" variant="warning" :title="$t('ads.create_campaign.wallet_not_ready')" class="mb-6">
      <p>{{ $t('ads.create_campaign.wallet_not_ready_desc') }}</p>
      <NuxtLink :to="localePath('/ads/settings')" class="inline-block text-xs font-medium hover:underline mt-1.5">
        {{ $t('ads.create_campaign.configure_wallet') }} &rarr;
      </NuxtLink>
    </UiAlert>

    <form @submit.prevent="createCampaign" class="space-y-6">
      <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <!-- Left column: form fields -->
        <div class="lg:col-span-3 space-y-6">
          <!-- Section 1: Ad Content -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6 space-y-4">
            <h2 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('ads.create_campaign.content_section') }}</h2>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.name') }}</label>
              <input v-model="form.name" type="text" required :placeholder="$t('ads.create_campaign.name_placeholder')" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
            </div>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.post_title') }}</label>
              <input v-model="form.postTitle" type="text" required :placeholder="$t('ads.create_campaign.post_title_placeholder')" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
            </div>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.post_content') }}</label>
              <AdsRichEditor
                v-model="form.postContent"
                :placeholder="$t('ads.create_campaign.post_content_placeholder')"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.link') }}</label>
              <input v-model="form.link" type="url" :placeholder="$t('ads.create_campaign.link_placeholder')" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
            </div>
          </div>

          <!-- Section 2: Banner Image -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6 space-y-3">
            <h2 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('ads.create_campaign.image_section') }}</h2>
            <AdsImageUpload
              ref="imageUploadRef"
              @file-selected="onImageSelected"
            />
          </div>

          <!-- Section 3: Linked Content -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6 space-y-3">
            <h2 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('ads.create_campaign.linked_content') }}</h2>
            <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.linked_content_desc') }}</p>
            <AdsLinkedContent
              v-model:linked-item-id="form.linkedItemId"
              v-model:linked-establishment-id="form.linkedEstablishmentId"
              @linked-item="linkedItemData = $event"
              @linked-establishment="linkedEstablishmentData = $event"
            />
          </div>

          <!-- Section 4: Payment -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6 space-y-4">
            <h2 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('ads.create_campaign.payment_section') }}</h2>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.reward') }}</label>
              <div class="flex gap-2 items-center">
                <input v-model.number="form.rewardSats" type="number" min="1" required :placeholder="$t('ads.create_campaign.reward_placeholder')" class="flex-1 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
                <span class="text-neutral-600 dark:text-neutral-400">sats</span>
              </div>
              <p v-if="rewardFiat" class="text-xs text-neutral-400 dark:text-neutral-500 mt-1">≈ {{ rewardFiat }}</p>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">{{ $t('ads.create_campaign.reward_help') }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.budget') }}</label>
              <div class="flex gap-2 items-center">
                <input v-model.number="form.budgetSats" type="number" min="1" required :placeholder="$t('ads.create_campaign.budget_placeholder')" class="flex-1 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
                <span class="text-neutral-600 dark:text-neutral-400">sats</span>
              </div>
              <p v-if="budgetFiat" class="text-xs text-neutral-400 dark:text-neutral-500 mt-1">≈ {{ budgetFiat }}</p>
              <p v-if="audienceData && audienceData.max_budget_sats > 0" class="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
                {{ $t('ads.create_campaign.recommended_budget', { sats: audienceData.max_budget_sats }) }}
              </p>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('ads.create_campaign.budget_help') }}</p>
            </div>

            <!-- Association donation -->
            <ClientOnly>
              <DonationPrompt v-if="form.budgetSats > 0" :source-amount-sats="form.budgetSats" />
            </ClientOnly>
          </div>

          <!-- Section 5: Targeting -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6 space-y-5">
            <h2 class="text-lg font-medium text-neutral-900 dark:text-neutral-100">{{ $t('ads.create_campaign.targeting') }}</h2>

            <!-- Gender + Age -->
            <div>
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.target_gender') }}</label>
              <select v-model="form.targetGender" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent">
                <option value="any">{{ $t('ads.profile.gender_any') }}</option>
                <option value="male">{{ $t('ads.profile.gender_male') }}</option>
                <option value="female">{{ $t('ads.profile.gender_female') }}</option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.age_from') }}</label>
                <input v-model.number="form.ageFrom" type="number" min="13" max="120" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
              </div>
              <div>
                <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">{{ $t('ads.create_campaign.age_to') }}</label>
                <input v-model.number="form.ageTo" type="number" min="13" max="120" class="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:ring-2 focus:ring-primary focus:border-transparent" />
              </div>
            </div>

            <!-- Interest targeting -->
            <div v-if="allInterests.length > 0" class="space-y-3">
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ $t('ads.create_campaign.interests') }}</label>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="interest in allInterests"
                  :key="interest.id"
                  type="button"
                  @click="toggleInterest(interest.id)"
                  class="px-2.5 py-1 text-xs rounded-full border transition-colors"
                  :class="form.targetInterestIds.includes(interest.id)
                    ? 'bg-primary/20 border-primary text-primary dark:text-primary'
                    : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  {{ $t(`ads.interests.${interest.slug}`, interest.name) }}
                </button>
              </div>
              <p class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.interests_help') }}</p>
            </div>

            <!-- Family targeting -->
            <div v-if="allChildrenAges.length > 0">
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ $t('ads.create_campaign.family_targeting') }}
              </label>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="age in allChildrenAges"
                  :key="age.id"
                  type="button"
                  @click="toggleTargetChildrenAge(age.id)"
                  class="px-2.5 py-1 text-xs rounded-full border transition-colors"
                  :class="form.targetChildrenAgeIds.includes(age.id)
                    ? 'bg-primary/20 border-primary text-primary dark:text-primary'
                    : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  {{ getChildrenAgeLabel(age.name) }}
                </button>
              </div>
              <p class="text-xs text-neutral-500 dark:text-neutral-400 mt-1.5">{{ $t('ads.create_campaign.family_targeting_help') }}</p>
            </div>

            <!-- Skills targeting -->
            <div v-if="allSkills.length > 0">
              <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {{ $t('ads.create_campaign.skills_targeting') }}
              </label>
              <div class="flex flex-wrap gap-2 mb-2">
                <button
                  v-for="skill in allSkills"
                  :key="skill.id"
                  type="button"
                  @click="toggleTargetSkill(skill.id)"
                  class="px-2.5 py-1 text-xs rounded-full border transition-colors"
                  :class="form.targetSkillIds.includes(skill.id)
                    ? 'bg-primary/20 border-primary text-primary dark:text-primary'
                    : 'border-neutral-300 dark:border-neutral-600 text-neutral-600 dark:text-neutral-400 hover:border-neutral-400 dark:hover:border-neutral-500'"
                >
                  {{ $t(`ads.skills.${skill.slug}`, skill.name) }}
                </button>
              </div>
              <div v-if="form.targetSkillIds.length > 0" class="flex items-center gap-3">
                <label class="text-sm text-neutral-600 dark:text-neutral-400">{{ $t('ads.create_campaign.min_skill_level') }}:</label>
                <select v-model.number="form.targetMinSkillLevel" class="px-3 py-1 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100">
                  <option :value="1">{{ $t('ads.create_campaign.skill_beginner_plus') }}</option>
                  <option :value="2">{{ $t('ads.create_campaign.skill_intermediate_plus') }}</option>
                  <option :value="3">{{ $t('ads.create_campaign.skill_advanced_plus') }}</option>
                  <option :value="4">{{ $t('ads.create_campaign.skill_expert_plus') }}</option>
                  <option :value="5">{{ $t('ads.create_campaign.skill_master_only') }}</option>
                </select>
              </div>
              <p v-else class="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{{ $t('ads.create_campaign.skills_targeting_help') }}</p>
            </div>

            <!-- Location targeting -->
            <div class="space-y-3 pt-1">
              <div class="flex items-center gap-3">
                <input
                  id="geo-toggle"
                  v-model="geoEnabled"
                  type="checkbox"
                  class="w-4 h-4 rounded border-neutral-300 dark:border-neutral-600 text-primary focus:ring-primary"
                />
                <label for="geo-toggle" class="text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ $t('ads.create_campaign.location_targeting') }}</label>
              </div>
              <p v-if="!geoEnabled" class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.location_targeting_help') }}</p>

              <template v-if="geoEnabled">
                <div
                  ref="geoMapEl"
                  class="w-full h-[250px] rounded-lg overflow-hidden border border-neutral-200 dark:border-neutral-600"
                />
                <p v-if="form.targetLatitude !== null" class="text-xs text-neutral-500 font-mono">
                  {{ form.targetLatitude.toFixed(6) }}, {{ form.targetLongitude!.toFixed(6) }}
                </p>
                <p v-else class="text-xs text-neutral-400">{{ $t('ads.create_campaign.click_map_to_target') }}</p>

                <div>
                  <label class="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    {{ $t('ads.create_campaign.radius_km') }}: {{ form.targetRadiusKm }} km
                  </label>
                  <input
                    v-model.number="form.targetRadiusKm"
                    type="range"
                    min="0.5"
                    max="50"
                    step="0.5"
                    class="w-full accent-primary"
                  />
                  <div class="flex justify-between text-xs text-neutral-400">
                    <span>0.5 km</span>
                    <span>50 km</span>
                  </div>
                </div>
              </template>
            </div>

            <!-- Self-targeting radio -->
            <div class="space-y-1.5">
              <label class="text-sm font-medium text-neutral-700 dark:text-neutral-300">{{ $t('ads.create_campaign.show_self_label') }}</label>
              <div class="flex flex-col gap-1.5 mt-1">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="selfMode" value="criteria" class="text-primary" />
                  <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('ads.create_campaign.self_criteria') }}</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="selfMode" value="include" />
                  <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('ads.create_campaign.self_include') }}</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="selfMode" value="exclude" />
                  <span class="text-sm text-neutral-700 dark:text-neutral-300">{{ $t('ads.create_campaign.self_exclude') }}</span>
                </label>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 justify-end">
            <button type="button" @click="navigateTo(localePath('/ads/campaigns'))" class="px-4 py-2 border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700">
              {{ $t('ads.create_campaign.cancel') }}
            </button>
            <button type="submit" :disabled="submitting" class="px-6 py-2.5 font-medium rounded-lg disabled:opacity-50 transition-colors" :class="advertiserWalletConfigured
              ? 'btn-primary'
              : 'bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-300 dark:hover:bg-neutral-600'
            ">
              {{ advertiserWalletConfigured ? $t('ads.create_campaign.create') : $t('ads.create_campaign.save_draft') }}
            </button>
          </div>
        </div>

        <!-- Right column: Preview + Audience estimate -->
        <div class="lg:col-span-2 space-y-6">
          <!-- Live Preview -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 lg:sticky lg:top-4">
            <h2 class="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-4">{{ $t('ads.create_campaign.preview_section') }}</h2>

            <!-- Preview card -->
            <div class="rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
              <!-- Preview image -->
              <img
                v-if="previewImageUrl"
                :src="previewImageUrl"
                alt="Preview"
                class="w-full h-[140px] object-cover"
              />

              <div class="p-3.5 space-y-2">
                <div class="flex items-start justify-between gap-2">
                  <h3 class="text-sm font-semibold text-neutral-900 dark:text-neutral-100 leading-snug line-clamp-2">
                    {{ form.postTitle || $t('ads.create_campaign.post_title_placeholder') }}
                  </h3>
                  <div v-if="form.rewardSats" class="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary text-black flex-shrink-0">
                    <Zap class="w-3 h-3" />
                    <span class="text-xs font-bold tabular-nums">{{ form.rewardSats }}</span>
                  </div>
                </div>

                <div
                  v-if="form.postContent && form.postContent !== '<p></p>'"
                  class="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed line-clamp-3 ads-preview-content"
                  v-html="form.postContent"
                />
                <p v-else class="text-xs text-neutral-400 dark:text-neutral-500 italic">
                  {{ $t('ads.create_campaign.post_content_placeholder') }}
                </p>

                <!-- Linked content preview -->
                <div
                  v-if="linkedItemData || linkedEstablishmentData"
                  class="flex items-center gap-2 p-2 rounded-lg bg-neutral-50 dark:bg-neutral-900 border border-neutral-100 dark:border-neutral-700/50"
                >
                  <div class="w-8 h-8 rounded-lg bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center flex-shrink-0">
                    <Package v-if="linkedItemData" class="w-3.5 h-3.5 text-neutral-400" />
                    <Building2 v-else class="w-3.5 h-3.5 text-neutral-400" />
                  </div>
                  <p class="text-xs font-medium text-neutral-700 dark:text-neutral-300 truncate">
                    {{ linkedItemData?.title || linkedEstablishmentData?.name }}
                  </p>
                </div>

                <div v-if="form.link" class="pt-1">
                  <span class="text-[10px] text-secondary dark:text-secondary-400 truncate block">{{ cleanUrl(form.link) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Audience estimate -->
          <div class="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5">
            <h2 class="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Users class="w-4 h-4" />
              {{ $t('ads.create_campaign.audience_reach') }}
            </h2>

            <div v-if="estimateLoading" class="text-center py-4">
              <Loader2 class="w-6 h-6 animate-spin text-neutral-400 mx-auto" />
              <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-2">{{ $t('ads.create_campaign.calculating') }}</p>
            </div>

            <div v-else-if="audienceData" class="space-y-4">
              <div class="text-center py-2">
                <p class="text-3xl font-bold text-neutral-900 dark:text-neutral-100">{{ audienceData.reach }}</p>
                <p class="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
                  {{ audienceData.reach > 0
                    ? $t('ads.create_campaign.estimated_reach', { count: audienceData.reach })
                    : $t('ads.create_campaign.no_profiles')
                  }}
                </p>
              </div>

              <div v-if="audienceData.reach > 0" class="border-t border-neutral-200 dark:border-neutral-700 pt-4 space-y-3">
                <div class="flex justify-between text-sm">
                  <span class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.full_coverage') }}</span>
                  <span class="font-semibold text-neutral-900 dark:text-neutral-100">{{ audienceData.max_budget_sats }} sats</span>
                </div>

                <!-- Breakdown -->
                <div v-if="audienceData.breakdown" class="space-y-2 pt-2 border-t border-neutral-100 dark:border-neutral-700">
                  <div v-if="audienceData.breakdown.by_gender">
                    <span class="text-xs text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.breakdown_gender') }}</span>
                    <div class="flex gap-1 mt-1 flex-wrap">
                      <span v-if="audienceData.breakdown.by_gender.male > 0" class="px-2 py-0.5 bg-secondary-100 dark:bg-secondary-900/30 text-secondary-700 dark:text-secondary-300 rounded text-xs">
                        ♂ {{ audienceData.breakdown.by_gender.male }}
                      </span>
                      <span v-if="audienceData.breakdown.by_gender.female > 0" class="px-2 py-0.5 bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300 rounded text-xs">
                        ♀ {{ audienceData.breakdown.by_gender.female }}
                      </span>
                      <span v-if="audienceData.breakdown.by_gender.any > 0" class="px-2 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded text-xs">
                        ✦ {{ audienceData.breakdown.by_gender.any }}
                      </span>
                    </div>
                  </div>
                  <div v-if="audienceData.breakdown.avg_age" class="flex justify-between text-xs">
                    <span class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.breakdown_avg_age') }}</span>
                    <span class="font-medium text-neutral-800 dark:text-neutral-200">{{ audienceData.breakdown.avg_age }} y.o.</span>
                  </div>
                  <div class="flex justify-between text-xs">
                    <span class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.breakdown_location') }}</span>
                    <span class="font-medium text-neutral-800 dark:text-neutral-200">{{ audienceData.breakdown.has_location }}/{{ audienceData.reach }}</span>
                  </div>
                  <div class="flex justify-between text-xs">
                    <span class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.breakdown_children') }}</span>
                    <span class="font-medium text-neutral-800 dark:text-neutral-200">{{ audienceData.breakdown.has_children }}</span>
                  </div>
                  <div class="flex justify-between text-xs">
                    <span class="text-neutral-500 dark:text-neutral-400">{{ $t('ads.create_campaign.breakdown_skills') }}</span>
                    <span class="font-medium text-neutral-800 dark:text-neutral-200">{{ audienceData.breakdown.has_skills }}</span>
                  </div>
                </div>

                <p class="text-xs text-neutral-400 dark:text-neutral-500">
                  {{ $t('ads.create_campaign.budget_excess_info') }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ArrowLeft, Users, Loader2, Zap, Package, Building2 } from 'lucide-vue-next'

const { t } = useI18n()
const authStore = useAuthStore()
const localePath = useLocalePath()
const colorMode = useColorMode()
const { mapCenter: savedMapCenter, mapZoom: savedMapZoom } = useMapState()
const { advertiserWalletConfigured, walletProvider, profileLoaded, loadAdsProfile } = useAdsState()
const { satsToFiat, formatFiat, fetchBtcPrice } = useBtcPrice()

const rewardFiat = computed(() => formatFiat(satsToFiat(form.value.rewardSats)))
const budgetFiat = computed(() => formatFiat(satsToFiat(form.value.budgetSats)))

const imageUploadRef = ref<any>(null)
const pendingImageFile = ref<File | null>(null)
const previewImageUrl = ref<string | null>(null)
const linkedItemData = ref<any>(null)
const linkedEstablishmentData = ref<any>(null)

function onImageSelected(file: File | null) {
  if (file) {
    pendingImageFile.value = file
    previewImageUrl.value = URL.createObjectURL(file)
  } else {
    pendingImageFile.value = null
    previewImageUrl.value = null
  }
}

function cleanUrl(url: string): string {
  try {
    const u = new URL(url)
    return u.hostname + (u.pathname !== '/' ? u.pathname : '')
  } catch {
    return url
  }
}

const form = ref({
  name: '',
  postTitle: '',
  postContent: '',
  link: '',
  rewardSats: 10,
  budgetSats: 1000,
  targetGender: 'any',
  ageFrom: 18,
  ageTo: 65,
  targetInterestIds: [] as string[],
  targetChildrenAgeIds: [] as string[],
  targetSkillIds: [] as string[],
  targetMinSkillLevel: 1,
  targetLatitude: null as number | null,
  targetLongitude: null as number | null,
  targetRadiusKm: 5,
  includeSelf: false,
  excludeSelf: false,
  linkedItemId: null as string | null,
  linkedEstablishmentId: null as string | null,
})

// Self-targeting radio
const selfMode = ref<'criteria' | 'include' | 'exclude'>('criteria')
watch(selfMode, (v) => {
  form.value.includeSelf = v === 'include'
  form.value.excludeSelf = v === 'exclude'
})

// Geo targeting map
const geoEnabled = ref(false)
const geoMapEl = ref<HTMLElement | null>(null)
let geoMap: any = null
let geoMarker: any = null
let geoCircleAdded = false

const getStyleUrl = () =>
  colorMode.value === 'dark'
    ? '/map-styles/dark-liberty-parahub.json'
    : '/map-styles/liberty-parahub.json'

async function initGeoMap() {
  if (geoMap || !geoMapEl.value) return
  const mod = await import('maplibre-gl')
  const maplibregl = mod.default || mod
  await import('maplibre-gl/dist/maplibre-gl.css')

  geoMap = new maplibregl.Map({
    container: geoMapEl.value,
    style: getStyleUrl(),
    center: savedMapCenter.value,
    zoom: Math.min(savedMapZoom.value, 12),
    attributionControl: false,
    fadeDuration: 0,
  })
  geoMap.once('load', () => {
    geoMap.resize()
    if (form.value.targetLatitude !== null) updateGeoCircle()
  })

  geoMap.on('click', (e: any) => {
    const { lng, lat } = e.lngLat
    form.value.targetLatitude = Math.round(lat * 1e6) / 1e6
    form.value.targetLongitude = Math.round(lng * 1e6) / 1e6
    if (geoMarker) {
      geoMarker.setLngLat([lng, lat])
    } else {
      geoMarker = new maplibregl.Marker({ color: '#FFE216' })
        .setLngLat([lng, lat])
        .addTo(geoMap)
    }
    updateGeoCircle()
    fitToCircle()
  })

  geoMap.on('style.load', () => {
    geoCircleAdded = false
    if (form.value.targetLatitude !== null) updateGeoCircle()
  })
}

function destroyGeoMap() {
  if (geoMap) {
    geoMap.remove()
    geoMap = null
    geoMarker = null
    geoCircleAdded = false
  }
}

function makeCircleGeoJSON(lng: number, lat: number, radiusKm: number) {
  const steps = 64
  const coords = []
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI
    const dx = radiusKm / (111.32 * Math.cos((lat * Math.PI) / 180))
    const dy = radiusKm / 110.574
    coords.push([lng + dx * Math.cos(angle), lat + dy * Math.sin(angle)])
  }
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } }
}

function updateGeoCircle() {
  if (!geoMap || form.value.targetLatitude === null || form.value.targetLongitude === null) return
  const geojson = makeCircleGeoJSON(form.value.targetLongitude, form.value.targetLatitude, form.value.targetRadiusKm)

  if (geoCircleAdded) {
    const src = geoMap.getSource('radius-circle')
    if (src) src.setData(geojson)
  } else {
    geoMap.addSource('radius-circle', { type: 'geojson', data: geojson })
    geoMap.addLayer({
      id: 'radius-circle-fill',
      type: 'fill',
      source: 'radius-circle',
      paint: { 'fill-color': '#FFE216', 'fill-opacity': 0.2 },
    })
    geoMap.addLayer({
      id: 'radius-circle-line',
      type: 'line',
      source: 'radius-circle',
      paint: { 'line-color': '#FFE216', 'line-width': 2.5, 'line-opacity': 0.7 },
    })
    geoCircleAdded = true
  }
}

watch(geoEnabled, (val) => {
  if (val) {
    nextTick(() => initGeoMap())
  } else {
    destroyGeoMap()
    form.value.targetLatitude = null
    form.value.targetLongitude = null
    form.value.targetRadiusKm = 5
  }
})

function fitToCircle() {
  if (!geoMap || form.value.targetLatitude === null || form.value.targetLongitude === null) return
  const lat = form.value.targetLatitude
  const lng = form.value.targetLongitude
  const r = form.value.targetRadiusKm
  const dLat = r / 110.574
  const dLng = r / (111.32 * Math.cos((lat * Math.PI) / 180))
  geoMap.fitBounds(
    [[lng - dLng, lat - dLat], [lng + dLng, lat + dLat]],
    { padding: 30, maxZoom: 15, duration: 500 }
  )
}

watch(() => form.value.targetRadiusKm, () => {
  updateGeoCircle()
  fitToCircle()
})

watch(() => colorMode.value, () => {
  if (geoMap) geoMap.setStyle(getStyleUrl())
})

onUnmounted(() => destroyGeoMap())

// Reference data
const allInterests = ref<{ id: string; slug: string; name: string }[]>([])
const allSkills = ref<{ id: string; slug: string; name: string }[]>([])
const allChildrenAges = ref<{ id: string; name: string }[]>([])

const childrenAgeKeyMap: Record<string, string> = {
  'Infant (0-2 years)': 'infant',
  'Toddler (2-4 years)': 'toddler',
  'Preschool (4-6 years)': 'preschool',
  'Elementary (6-12 years)': 'elementary',
  'Teen (12-18 years)': 'teen',
  '18+': 'eighteen_plus',
  'No children': 'no_children',
}

function getChildrenAgeLabel(name: string): string {
  const key = childrenAgeKeyMap[name]
  return key ? t(`ads.children_ages.${key}`, name) : name
}

async function loadReferenceData() {
  try {
    await authStore.ensureToken()
    const [interests, skills, childrenAges] = await Promise.all([
      $fetch<any[]>('/api/v1/ads/interests/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
      }),
      $fetch<any[]>('/api/v1/ads/skills/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
      }),
      $fetch<any[]>('/api/v1/ads/children-ages/', {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
      }),
    ])
    allInterests.value = interests
    allSkills.value = skills
    const noIdx = childrenAges.findIndex((a: any) => a.name === 'No children')
    if (noIdx > 0) {
      const [nc] = childrenAges.splice(noIdx, 1)
      childrenAges.unshift(nc)
    }
    allChildrenAges.value = childrenAges
  } catch (error) {
    console.error('Failed to load reference data:', error)
  }
}

function toggleInterest(id: string) {
  const idx = form.value.targetInterestIds.indexOf(id)
  if (idx >= 0) form.value.targetInterestIds.splice(idx, 1)
  else form.value.targetInterestIds.push(id)
}

function toggleTargetChildrenAge(id: string) {
  const idx = form.value.targetChildrenAgeIds.indexOf(id)
  if (idx >= 0) form.value.targetChildrenAgeIds.splice(idx, 1)
  else form.value.targetChildrenAgeIds.push(id)
}

function toggleTargetSkill(id: string) {
  const idx = form.value.targetSkillIds.indexOf(id)
  if (idx >= 0) form.value.targetSkillIds.splice(idx, 1)
  else form.value.targetSkillIds.push(id)
}

const submitting = ref(false)
const estimateLoading = ref(false)

interface AudienceBreakdown {
  by_gender: { male: number; female: number; any: number }
  avg_age: number | null
  has_location: number
  has_children: number
  has_skills: number
}
interface AudienceData {
  reach: number
  max_budget_sats: number
  breakdown?: AudienceBreakdown
}
const audienceData = ref<AudienceData | null>(null)

let estimateTimer: ReturnType<typeof setTimeout> | null = null
let estimateAbort: AbortController | null = null

function fetchEstimateDebounced() {
  if (estimateTimer) clearTimeout(estimateTimer)
  estimateTimer = setTimeout(fetchEstimate, 500)
}

async function fetchEstimate() {
  if (estimateAbort) estimateAbort.abort()
  estimateAbort = new AbortController()
  const signal = estimateAbort.signal

  estimateLoading.value = true
  try {
    await authStore.ensureToken()
    const params = new URLSearchParams({
      target_gender: form.value.targetGender,
      target_age_from: String(form.value.ageFrom),
      target_age_to: String(form.value.ageTo),
      reward_sats: String(form.value.rewardSats || 1),
      target_interest_ids: form.value.targetInterestIds.join(','),
      target_children_age_ids: form.value.targetChildrenAgeIds.join(','),
      target_skill_ids: form.value.targetSkillIds.join(','),
      target_min_skill_level: String(form.value.targetMinSkillLevel),
      include_self: String(form.value.includeSelf),
      exclude_self: String(form.value.excludeSelf),
    })
    if (geoEnabled.value && form.value.targetLatitude !== null && form.value.targetLongitude !== null) {
      params.set('target_latitude', String(form.value.targetLatitude))
      params.set('target_longitude', String(form.value.targetLongitude))
      params.set('target_radius_km', String(form.value.targetRadiusKm))
    }
    const result = await $fetch<AudienceData>(
      `/api/v1/ads/audience-estimate/?${params}`,
      {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
        signal,
      }
    )
    if (!signal.aborted) audienceData.value = result
  } catch (error: any) {
    if (error?.name !== 'AbortError') console.error('Failed to fetch audience estimate:', error)
  } finally {
    if (!signal.aborted) estimateLoading.value = false
  }
}

onMounted(() => {
  if (!profileLoaded.value) loadAdsProfile()
  loadReferenceData()
  fetchBtcPrice()
})

// Watch targeting fields for debounced audience estimate
watch(
  () => [
    form.value.targetGender,
    form.value.ageFrom,
    form.value.ageTo,
    form.value.rewardSats,
    form.value.targetInterestIds.length,
    form.value.targetChildrenAgeIds.length,
    form.value.targetSkillIds.length,
    form.value.targetMinSkillLevel,
    geoEnabled.value,
    form.value.targetLatitude,
    form.value.targetRadiusKm,
    form.value.includeSelf,
    form.value.excludeSelf,
  ],
  fetchEstimateDebounced,
  { immediate: true }
)

const donation = useDonation()

async function createCampaign() {
  submitting.value = true
  try {
    await authStore.ensureToken()
    const res = await $fetch<any>('/api/v1/ads/campaigns/', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Authorization': `Bearer ${authStore.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: form.value.name,
        post_title: form.value.postTitle,
        post_content: form.value.postContent,
        link: form.value.link,
        reward_sats: form.value.rewardSats,
        budget_sats: form.value.budgetSats,
        target_gender: form.value.targetGender,
        target_age_from: form.value.ageFrom,
        target_age_to: form.value.ageTo,
        target_interest_ids: form.value.targetInterestIds,
        target_children_age_ids: form.value.targetChildrenAgeIds,
        target_skill_ids: form.value.targetSkillIds,
        target_min_skill_level: form.value.targetMinSkillLevel,
        target_latitude: geoEnabled.value ? form.value.targetLatitude : null,
        target_longitude: geoEnabled.value ? form.value.targetLongitude : null,
        target_radius_km: geoEnabled.value ? form.value.targetRadiusKm : 0,
        include_self: form.value.includeSelf,
        exclude_self: form.value.excludeSelf,
        linked_item_id: form.value.linkedItemId,
        linked_establishment_id: form.value.linkedEstablishmentId,
      })
    })

    // Upload image if pending
    if (pendingImageFile.value && res.id) {
      const formData = new FormData()
      formData.append('image', pendingImageFile.value)
      await $fetch(`/api/v1/ads/campaigns/${res.id}/image/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${authStore.token}` },
        body: formData,
      })
    }

    // Record donation/skip for analytics
    const donationSats = donation.calcDonationSats(form.value.budgetSats)
    await donation.recordDonation({
      source: 'ADS_CAMPAIGN',
      sourceAmountSats: form.value.budgetSats,
      donationAmountSats: donationSats,
      supportLevelAtTime: donation.supportLevel.value,
      status: donationSats > 0 ? 'COMPLETED' : 'SKIPPED',
    })

    navigateTo(localePath('/ads/campaigns'))
  } catch (error) {
    console.error('Failed to create campaign:', error)
  } finally {
    submitting.value = false
  }
}

definePageMeta({
  middleware: 'auth',
})
</script>

<style>
.ads-preview-content a { color: #4E4EC8; text-decoration: underline; }
.ads-preview-content ul { list-style: disc; padding-left: 1rem; }
.ads-preview-content ol { list-style: decimal; padding-left: 1rem; }
.ads-preview-content blockquote { border-left: 2px solid #4E4EC8; padding-left: 0.5rem; color: #9ca3af; }
</style>
