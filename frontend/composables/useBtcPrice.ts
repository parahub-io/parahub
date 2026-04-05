import { ref, computed, watch } from 'vue'

// BTC price cache (shared between all instances)
const btcPrices = ref<Record<string, number>>({})
const lastFetchTime = ref(0)
const loading = ref(false)
const CACHE_DURATION = 60 * 1000 // 1 minute cache

// CoinGecko API (free, no key needed)
const COINGECKO_API = 'https://api.coingecko.com/api/v3/simple/price'

export function useBtcPrice() {
  const userCurrency = useLocalPref('preferred_currency', 'EUR')

  // Supported fiat currencies for conversion
  const supportedFiat = ['EUR', 'USD', 'RUB', 'GBP'] as const

  // Current BTC price in user's preferred currency
  const btcPrice = computed(() => {
    const currency = userCurrency.value?.toLowerCase()
    if (!currency || currency === 'btc') return null
    return btcPrices.value[currency] || null
  })

  // Fetch BTC price from CoinGecko
  const fetchBtcPrice = async (force = false) => {
    // Skip if already loading or cache is fresh
    const now = Date.now()
    if (loading.value || (!force && now - lastFetchTime.value < CACHE_DURATION)) {
      return
    }

    loading.value = true
    try {
      const currencies = supportedFiat.join(',')
      const response = await $fetch<{ bitcoin: Record<string, number> }>(
        `${COINGECKO_API}?ids=bitcoin&vs_currencies=${currencies}`
      )

      if (response?.bitcoin) {
        btcPrices.value = response.bitcoin
        lastFetchTime.value = now
      }
    } catch (error) {
      console.error('Failed to fetch BTC price:', error)
    } finally {
      loading.value = false
    }
  }

  // Convert sats to fiat
  const satsToFiat = (sats: number): number | null => {
    if (!btcPrice.value || !sats) return null
    const btc = sats / 100_000_000
    return btc * btcPrice.value
  }

  // Convert BTC to fiat
  const btcToFiat = (btc: number): number | null => {
    if (!btcPrice.value || !btc) return null
    return btc * btcPrice.value
  }

  // Convert fiat to sats
  const fiatToSats = (fiat: number): number | null => {
    if (!btcPrice.value || !fiat) return null
    const btc = fiat / btcPrice.value
    return Math.round(btc * 100_000_000)
  }

  // Format fiat amount with currency symbol
  const formatFiat = (amount: number | null): string => {
    if (amount === null) return ''
    const currency = userCurrency.value
    if (currency === 'BTC') return ''

    const symbols: Record<string, string> = {
      EUR: '€',
      USD: '$',
      RUB: '₽',
      GBP: '£'
    }

    const symbol = symbols[currency] || currency
    const formatted = amount.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })

    // Symbol position depends on currency
    if (currency === 'USD' || currency === 'GBP') {
      return `${symbol}${formatted}`
    }
    return `${formatted} ${symbol}`
  }

  return {
    btcPrice,
    btcPrices,
    loading,
    userCurrency,
    fetchBtcPrice,
    satsToFiat,
    btcToFiat,
    fiatToSats,
    formatFiat
  }
}
