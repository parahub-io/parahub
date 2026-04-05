/**
 * Association donation composable — manages donation prompt state and execution.
 * Singleton module-level state (same pattern as useAdsState).
 */

// Module-level state (shared across all component instances)
const associationSparkAddress = ref('')
const associationLnAddress = ref('')
const configLoaded = ref(false)

const STORAGE_KEY = 'parahub_support_level'
const ONBOARDED_KEY = 'parahub_donation_onboarded'

export function useDonation() {
  const authStore = useAuthStore()
  const { satsToFiat, formatFiat, userCurrency } = useBtcPrice()

  // Support level: from localStorage (sticky), fallback to profile, fallback to 0.1
  const supportLevel = ref<number>(0.1)

  const initSupportLevel = () => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored !== null) {
      supportLevel.value = parseFloat(stored)
    } else if (authStore.profile?.support_level !== undefined) {
      supportLevel.value = parseFloat(String(authStore.profile.support_level))
    } else {
      supportLevel.value = 0.1
    }
  }

  const setSupportLevel = (level: number) => {
    supportLevel.value = level
    localStorage.setItem(STORAGE_KEY, String(level))
  }

  const isOnboarded = computed(() => localStorage.getItem(ONBOARDED_KEY) === '1')

  const markOnboarded = () => {
    localStorage.setItem(ONBOARDED_KEY, '1')
  }

  // Calculate donation amount in sats
  const calcDonationSats = (sourceSats: number): number => {
    if (supportLevel.value <= 0) return 0
    return Math.ceil(sourceSats * supportLevel.value / 100)
  }

  // Format donation amount for display
  const formatDonationFiat = (sats: number): string | null => {
    if (sats <= 0 || userCurrency.value === 'BTC') return null
    const fiat = satsToFiat(sats)
    if (fiat === null) return null
    return formatFiat(fiat)
  }

  // Fetch association addresses from API
  const loadConfig = async () => {
    if (configLoaded.value) return
    try {
      const res = await $fetch<any>('/api/v1/income/config/', {
        credentials: 'include',
        headers: authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {},
      })
      associationSparkAddress.value = res.spark_address || ''
      associationLnAddress.value = res.ln_address || ''
      configLoaded.value = true
    } catch {
      // Non-critical — donation just won't work
    }
  }

  // Record donation on server
  const recordDonation = async (params: {
    source: 'WALLET_SEND' | 'ADS_CAMPAIGN' | 'MANUAL'
    sourceAmountSats: number
    donationAmountSats: number
    supportLevelAtTime: number
    lnPaymentHash?: string
    status: 'COMPLETED' | 'SKIPPED' | 'FAILED'
  }) => {
    try {
      await authStore.ensureToken()
      await $fetch('/api/v1/income/donations/', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: {
          source: params.source,
          source_amount_sats: params.sourceAmountSats,
          donation_amount_sats: params.donationAmountSats,
          support_level_at_time: params.supportLevelAtTime,
          ln_payment_hash: params.lnPaymentHash || '',
          status: params.status,
        },
      })
    } catch {
      // Non-critical
    }
  }

  const hasAssociationAddress = computed(() =>
    !!(associationSparkAddress.value || associationLnAddress.value)
  )

  return {
    supportLevel,
    associationSparkAddress,
    associationLnAddress,
    hasAssociationAddress,
    configLoaded,
    isOnboarded,
    initSupportLevel,
    setSupportLevel,
    markOnboarded,
    calcDonationSats,
    formatDonationFiat,
    loadConfig,
    recordDonation,
  }
}
