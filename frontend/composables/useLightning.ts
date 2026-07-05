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
// True only after the first successful getInfo(). Gates the UI so it shows a
// loading skeleton instead of a premature, misleading 0 while the SDK reports
// `ready` but the background sync hasn't landed the real balance yet.
const balanceLoaded = ref(false)
const lightningAddress = ref<LightningAddressInfo | null>(null)
const eventListenerId = ref<string | null>(null)
const unclaimedDeposits = ref<DepositInfo[]>([])
const depositAddress = ref<string | null>(null)
const paymentEventVersion = ref(0)

// Singleton init promise to prevent double-init
let initPromise: Promise<void> | null = null

// Cross-tab coordination: a tab taking the wallet over asks others to release.
let broadcast: BroadcastChannel | null = null
let releaseListenerRegistered = false

export const useLightning = () => {
  const { loadSeed, hasSeed } = useSeed()

  // Hold the Web Lock for as long as this tab keeps the SDK connected.
  const holdUntilDisconnect = () => new Promise<boolean>((resolve) => {
    const check = setInterval(() => {
      if (!sdkInstance.value || sdkState.value !== 'ready') {
        clearInterval(check)
        resolve(true)
      }
    }, 1000)
  })

  const getBroadcast = (): BroadcastChannel | null => {
    if (!process.client || typeof BroadcastChannel === 'undefined') return null
    if (!broadcast) broadcast = new BroadcastChannel('parahub-wallet')
    return broadcast
  }

  // When another tab takes the wallet over, disconnect here so only one SDK
  // ever writes to the shared IndexedDB store.
  const registerReleaseListener = () => {
    const ch = getBroadcast()
    if (!ch || releaseListenerRegistered) return
    releaseListenerRegistered = true
    ch.addEventListener('message', (ev: MessageEvent) => {
      // Another tab took the wallet over: drop our SDK (so only one tab writes
      // to IndexedDB) and show the locked-out state pointing at that tab.
      if (ev.data?.type === 'wallet-takeover' && sdkInstance.value) {
        disconnect().then(() => {
          sdkState.value = 'error'
          sdkError.value = 'walletOpenInAnotherTab'
        })
      }
    })
  }

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

    // Only one tab may drive the SDK at a time — concurrent IndexedDB writers
    // would corrupt wallet state. Coordinate via a named Web Lock.
    // Release our lock if any other tab takes the wallet over.
    registerReleaseListener()

    if ('locks' in navigator) {
      try {
        // Signal init completion without waiting for the lock to be released.
        let initResolve!: () => void
        const initDone = new Promise<void>(r => { initResolve = r })
        let gotLock = false

        // Fast path: grab the lock if it's free right now (don't await — the
        // callback holds the lock until the SDK disconnects).
        navigator.locks.request('parahub-breez-sdk', { ifAvailable: true }, async (lock) => {
          if (!lock) {
            initResolve() // lock busy — let the caller fall through to the wait path
            return false
          }
          gotLock = true
          await _initializeBreez()
          initResolve() // Signal: init complete, callers can proceed
          return holdUntilDisconnect()
        }).catch(() => {}) // our lock rejects if another tab later steals it

        // Resolve as soon as the fast path settles, or after 2s for a slow init.
        await Promise.race([
          initDone.then(() => true),
          new Promise<false>((resolve) => setTimeout(() => resolve(false), 2000))
        ])

        // Lock is held by another tab: surface the intended message instead of
        // hanging on skeletons, and auto-recover once that tab releases the lock.
        if (!gotLock) {
          sdkState.value = 'error'
          sdkError.value = 'walletOpenInAnotherTab'
          navigator.locks.request('parahub-breez-sdk', async (lock) => {
            if (sdkInstance.value) return true // already connected in this tab
            sdkState.value = 'initializing'
            await _initializeBreez()
            return holdUntilDisconnect()
          }).catch(() => {})
        }
      } catch (e) {
        // Fallback: try without lock (old browsers / locks unavailable)
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

      // Render the cached balance immediately: getInfo() reads local storage
      // (IndexedDB), no network — so a returning user sees their last-known
      // balance in ~0ms instead of waiting ~3-4s for the full network sync.
      // Breez-recommended pattern: show the cached balance now, then reconcile
      // via the background sync below and the `synced` event handler.
      refreshBalance()

      // Background: full network sync, then reconcile balance/deposits/LN address.
      ;(async () => {
        try { await sdk.syncWallet({}) } catch {}
        await Promise.allSettled([
          refreshBalance(),
          fetchUnclaimedDeposits(),
          sdk.getLightningAddress().then(info => {
            lightningAddress.value = info ?? null
          }).catch(() => {})
        ])
        // Best-effort init finished: reveal the balance even if getInfo failed,
        // so the card never gets stuck on the loading skeleton forever.
        balanceLoaded.value = true
      })()
    } catch (e: any) {
      console.error('Breez SDK init failed:', e)
      sdkState.value = 'error'
      sdkError.value = e.message || 'initFailed'
    }
  }

  /**
   * Force this tab to take over a wallet that's locked by another tab.
   * Asks live tabs to disconnect first (clean handoff — no concurrent writers),
   * then steals the Web Lock so a frozen/crashed tab can't keep us locked out.
   * User-initiated only.
   */
  const takeOverLock = async (): Promise<void> => {
    if (!process.client) return
    registerReleaseListener()
    getBroadcast()?.postMessage({ type: 'wallet-takeover' })
    sdkError.value = null
    sdkState.value = 'initializing'
    // Give a live holder a moment to release before we force it.
    await new Promise(r => setTimeout(r, 250))

    if (!('locks' in navigator)) {
      await _initializeBreez()
      return
    }

    let initResolve!: () => void
    const initDone = new Promise<void>(r => { initResolve = r })
    navigator.locks.request('parahub-breez-sdk', { steal: true }, async () => {
      await _initializeBreez()
      initResolve() // Signal: init complete, callers can proceed
      return holdUntilDisconnect()
    }).catch(() => initResolve())
    await initDone
  }

  /**
   * Read balance from local SDK state. Cheap, no network sync, emits no events.
   *
   * IMPORTANT: do NOT call syncWallet() here. This runs from the `synced` event
   * handler, and syncWallet() itself fires `synced` — syncing here creates a
   * sync storm (slow load, balance flicker, repeated history reloads). Keep the
   * network sync explicit via syncAndRefresh().
   */
  const refreshBalance = async (): Promise<void> => {
    if (!sdkInstance.value) return
    try {
      const info = await sdkInstance.value.getInfo({})
      balanceSats.value = info.balanceSats
      balanceLoaded.value = true
    } catch (e) {
      console.error('Failed to refresh balance:', e)
    }
  }

  /**
   * Force a network sync, then read the fresh balance. For user-initiated
   * refreshes (the refresh button, post-send) only — never the event handler.
   */
  const syncAndRefresh = async (): Promise<void> => {
    if (!sdkInstance.value) return
    try { await sdkInstance.value.syncWallet({}) } catch {}
    await refreshBalance()
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
      balanceLoaded.value = false
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
    balanceLoaded,
    lightningAddress,
    unclaimedDeposits,
    depositAddress,

    // Lifecycle
    initSdk,
    takeOverLock,
    disconnect,

    // Balance
    refreshBalance,
    syncAndRefresh,

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
