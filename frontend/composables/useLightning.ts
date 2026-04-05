/**
 * Lightning Wallet composable for Parahub
 *
 * Wraps Breez SDK Spark (WASM) for non-custodial Lightning payments.
 * Same BIP39 mnemonic from useSeed.ts = BTC + LN + PGP.
 *
 * Key design:
 * - Singleton: module-level refs shared across all consumers
 * - Multi-tab lock via navigator.locks API
 * - Lazy WASM loading via dynamic import
 * - Event-driven balance updates
 */

import { ref } from 'vue'
import { useSeed } from './useSeed'

import type {
  BreezSdk,
  Payment,
  InputType,
  PrepareSendPaymentResponse,
  PrepareLnurlPayResponse,
  LnurlPayRequestDetails,
  ReceivePaymentResponse,
  Rate,
  SdkEvent,
  LightningAddressInfo,
  DepositInfo,
  ClaimDepositResponse
} from '@breeztech/breez-sdk-spark/web'

// Singleton state (module-level, shared across all component instances)
const sdkInstance = ref<BreezSdk | null>(null)
const sdkState = ref<'idle' | 'initializing' | 'ready' | 'error'>('idle')
const sdkError = ref<string | null>(null)
const balanceSats = ref(0)
const lightningAddress = ref<LightningAddressInfo | null>(null)
const eventListenerId = ref<string | null>(null)
const unclaimedDeposits = ref<DepositInfo[]>([])
const depositAddress = ref<string | null>(null)
const paymentEventVersion = ref(0)

// Singleton init promise to prevent double-init
let initPromise: Promise<void> | null = null

export const useLightning = () => {
  const { loadSeed, hasSeed } = useSeed()

  /**
   * Initialize Breez SDK with mnemonic from localStorage.
   * Uses navigator.locks to prevent multiple tabs from connecting.
   */
  const initSdk = async (): Promise<void> => {
    if (!process.client) return
    if (sdkState.value === 'ready' && sdkInstance.value) return
    if (initPromise) return initPromise

    initPromise = _doInit()
    try {
      await initPromise
    } finally {
      initPromise = null
    }
  }

  const _doInit = async (): Promise<void> => {
    sdkState.value = 'initializing'
    sdkError.value = null

    // Check for multi-tab lock
    if ('locks' in navigator) {
      try {
        // Separate promise to signal init completion without waiting for lock release
        let initResolve!: () => void
        const initDone = new Promise<void>(r => { initResolve = r })

        // Fire lock request (don't await — it holds the lock until disconnect)
        navigator.locks.request('parahub-breez-sdk', { ifAvailable: true }, async (lock) => {
          if (!lock) {
            initResolve()
            return false
          }
          await _initializeBreez()
          initResolve() // Signal: init complete, callers can proceed
          // Hold lock until SDK disconnects
          return new Promise<boolean>((resolve) => {
            const check = setInterval(() => {
              if (!sdkInstance.value || sdkState.value !== 'ready') {
                clearInterval(check)
                resolve(true)
              }
            }, 1000)
          })
        })

        // Wait for init OR 2s timeout (lock held by another tab)
        const ready = await Promise.race([
          initDone.then(() => true),
          new Promise<false>((resolve) => setTimeout(() => resolve(false), 2000))
        ])

        if (!ready && sdkState.value !== 'ready') {
          sdkState.value = 'error'
          sdkError.value = 'walletOpenInAnotherTab'
          return
        }
      } catch (e) {
        // Fallback: try without lock (old browsers)
        await _initializeBreez()
      }
    } else {
      await _initializeBreez()
    }
  }

  const _initializeBreez = async (): Promise<void> => {
    try {
      const words = loadSeed()
      if (!words) {
        sdkState.value = 'error'
        sdkError.value = 'noSeed'
        return
      }

      // Dynamic import for WASM lazy loading
      const breez = await import('@breeztech/breez-sdk-spark/web')
      const initWasm = breez.default
      await initWasm()

      const config = useRuntimeConfig()
      const apiKey = config.public.breezApiKey as string

      // Get default config and apply API key
      const sdkConfig = breez.defaultConfig('mainnet')
      if (apiKey) {
        sdkConfig.apiKey = apiKey
      }
      // Allow auto-claiming on-chain deposits with network-recommended fee + 5 sat/vB leeway
      sdkConfig.maxDepositClaimFee = { type: 'networkRecommended', leewaySatPerVbyte: 5 }

      const mnemonic = words.join(' ')

      // Use SdkBuilder for web environment with IndexedDB storage
      let builder = breez.SdkBuilder.new(sdkConfig, { type: 'mnemonic', mnemonic })
      builder = await builder.withDefaultStorage('parahub-wallet')
      const sdk = await builder.build()

      sdkInstance.value = sdk

      // Register event listener for reactive updates
      eventListenerId.value = await sdk.addEventListener({
        onEvent: (e: SdkEvent) => {
          if (e.type === 'synced' || e.type === 'paymentSucceeded' || e.type === 'paymentPending') {
            refreshBalance()
            paymentEventVersion.value++

            // In-app toast for incoming payments
            if ((e.type === 'paymentSucceeded' || e.type === 'paymentPending') && 'payment' in e) {
              const p = (e as any).payment
              if (p?.paymentType === 'receive') {
                const amt = Number(p.amount)
                if (amt > 0) {
                  import('~/stores/toast').then(({ useToastStore }) => {
                    try { useToastStore().success(`+${amt.toLocaleString()} sats`) } catch {}
                  }).catch(() => {})
                }
              }
            }
          }
          if (e.type === 'claimedDeposits') {
            refreshBalance()
            // Remove claimed from unclaimed list
            fetchUnclaimedDeposits()
          }
          if (e.type === 'unclaimedDeposits') {
            unclaimedDeposits.value = e.unclaimedDeposits
          }
        }
      })

      sdkState.value = 'ready'

      // Background: sync, balance, deposits, LN address (non-blocking)
      ;(async () => {
        try { await sdk.sync() } catch {}
        await Promise.allSettled([
          refreshBalance(),
          fetchUnclaimedDeposits(),
          sdk.getLightningAddress().then(info => {
            lightningAddress.value = info ?? null
          }).catch(() => {})
        ])
      })()
    } catch (e: any) {
      console.error('Breez SDK init failed:', e)
      sdkState.value = 'error'
      sdkError.value = e.message || 'initFailed'
    }
  }

  /**
   * Refresh balance from SDK
   */
  const refreshBalance = async (): Promise<void> => {
    if (!sdkInstance.value) return
    try {
      try { await sdkInstance.value.sync() } catch {}
      const info = await sdkInstance.value.getInfo({})
      balanceSats.value = info.balanceSats
    } catch (e) {
      console.error('Failed to refresh balance:', e)
    }
  }

  /**
   * Generate a bolt11 Lightning invoice
   */
  const createInvoice = async (amountSats: number, description?: string): Promise<ReceivePaymentResponse> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.receivePayment({
      paymentMethod: {
        type: 'bolt11Invoice',
        description: description || 'Parahub payment',
        amountSats: amountSats,
      }
    })
  }

  /**
   * Get static reusable Spark address
   */
  const getSparkAddress = async (): Promise<ReceivePaymentResponse> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.receivePayment({
      paymentMethod: { type: 'sparkAddress' }
    })
  }

  /**
   * Get on-chain Bitcoin deposit address
   */
  const getBitcoinAddress = async (): Promise<ReceivePaymentResponse> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.receivePayment({
      paymentMethod: { type: 'bitcoinAddress' }
    })
  }

  /**
   * Get cached Bitcoin deposit address (avoids redundant SDK calls)
   */
  const getDepositAddress = async (): Promise<string> => {
    if (depositAddress.value) return depositAddress.value
    const result = await getBitcoinAddress()
    depositAddress.value = result.paymentRequest
    return result.paymentRequest
  }

  /**
   * Parse any payment input (bolt11, address, LNURL, LN-address, etc.)
   */
  const parseInput = async (input: string): Promise<InputType> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.parse(input)
  }

  /**
   * Prepare a send payment (validate + calculate fees)
   */
  const prepareSend = async (
    paymentRequest: string,
    amount?: bigint
  ): Promise<PrepareSendPaymentResponse> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.prepareSendPayment({
      paymentRequest,
      amount
    })
  }

  /**
   * Execute a prepared send payment
   */
  const executeSend = async (
    prepareResponse: PrepareSendPaymentResponse
  ): Promise<Payment> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const result = await sdkInstance.value.sendPayment({ prepareResponse })
    await refreshBalance()
    return result.payment
  }

  /**
   * Prepare LNURL-pay
   */
  const prepareLnurlPay = async (
    amountSats: number,
    payRequest: LnurlPayRequestDetails,
    comment?: string
  ): Promise<PrepareLnurlPayResponse> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.prepareLnurlPay({
      amountSats,
      payRequest,
      comment
    })
  }

  /**
   * Execute LNURL-pay
   */
  const executeLnurlPay = async (
    prepareResponse: PrepareLnurlPayResponse
  ): Promise<Payment> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const result = await sdkInstance.value.lnurlPay({ prepareResponse })
    await refreshBalance()
    return result.payment
  }

  /**
   * List payment history
   */
  const listPayments = async (limit = 50, offset = 0): Promise<Payment[]> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const result = await sdkInstance.value.listPayments({ limit, offset })
    return result.payments
  }

  /**
   * Register a Lightning address (username@breez.tips)
   */
  const registerLnAddress = async (username: string): Promise<LightningAddressInfo> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const info = await sdkInstance.value.registerLightningAddress({
      username,
      description: 'Parahub user'
    })
    lightningAddress.value = info
    return info
  }

  /**
   * Check if a Lightning address username is available
   */
  const checkLnAddressAvailable = async (username: string): Promise<boolean> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    return sdkInstance.value.checkLightningAddressAvailable({ username })
  }

  /**
   * Get current Lightning address
   */
  const getLnAddress = async (): Promise<LightningAddressInfo | undefined> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const info = await sdkInstance.value.getLightningAddress()
    lightningAddress.value = info ?? null
    return info
  }

  /**
   * Get fiat exchange rates from Breez
   */
  const getFiatRates = async (): Promise<Rate[]> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const result = await sdkInstance.value.listFiatRates()
    return result.rates
  }

  /**
   * Fetch unclaimed on-chain deposits
   */
  const fetchUnclaimedDeposits = async (): Promise<DepositInfo[]> => {
    if (!sdkInstance.value) return []
    try {
      const result = await sdkInstance.value.listUnclaimedDeposits({})
      unclaimedDeposits.value = result.deposits
      return result.deposits
    } catch (e) {
      console.error('Failed to fetch unclaimed deposits:', e)
      return []
    }
  }

  /**
   * Claim an on-chain deposit (convert to Spark balance)
   */
  const claimDeposit = async (txid: string, vout: number): Promise<ClaimDepositResponse> => {
    if (!sdkInstance.value) throw new Error('SDK not initialized')
    const result = await sdkInstance.value.claimDeposit({ txid, vout })
    await refreshBalance()
    await fetchUnclaimedDeposits()
    return result
  }

  /**
   * Disconnect and clean up SDK
   */
  const disconnect = async (): Promise<void> => {
    if (!sdkInstance.value) return
    try {
      if (eventListenerId.value) {
        await sdkInstance.value.removeEventListener(eventListenerId.value)
        eventListenerId.value = null
      }
      await sdkInstance.value.disconnect()
    } catch (e) {
      console.error('Breez SDK disconnect error:', e)
    } finally {
      sdkInstance.value = null
      sdkState.value = 'idle'
      balanceSats.value = 0
      lightningAddress.value = null
      unclaimedDeposits.value = []
      depositAddress.value = null
    }
  }

  /**
   * Format satoshis for display
   */
  const formatSats = (sats: number | bigint): string => {
    const n = typeof sats === 'bigint' ? Number(sats) : sats
    return n.toLocaleString()
  }

  return {
    // State
    sdkState,
    sdkError,
    balanceSats,
    lightningAddress,
    unclaimedDeposits,
    depositAddress,

    // Lifecycle
    initSdk,
    disconnect,

    // Balance
    refreshBalance,

    // Receive
    createInvoice,
    getSparkAddress,
    getBitcoinAddress,
    getDepositAddress,

    // Send
    parseInput,
    prepareSend,
    executeSend,
    prepareLnurlPay,
    executeLnurlPay,

    // Deposits
    fetchUnclaimedDeposits,
    claimDeposit,

    // History
    listPayments,
    paymentEventVersion,

    // Lightning Address
    registerLnAddress,
    checkLnAddressAvailable,
    getLnAddress,

    // Rates
    getFiatRates,

    // Helpers
    formatSats,
    hasSeed
  }
}
