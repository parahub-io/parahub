/**
 * Opt-in cross-device sync of client-side wallet context — tip batches and
 * payment annotations — as ONE ciphertext the server cannot read.
 *
 * The stores it syncs are localStorage-only by design (the server is never
 * told who paid whom); this module lets a user who explicitly enabled sync in
 * advanced preferences carry them between their own devices. Everything is
 * encrypted here, in the browser: AES-256-GCM under a key derived from the
 * BIP39 master seed (HKDF-SHA256, info "parahub-wallet-sync-v1"). The server
 * stores base64(iv || ciphertext) and learns only that an encrypted store
 * exists, its size and update times. Enabled state IS the server row: PUT
 * enables, DELETE disables and deletes.
 *
 * A device holding a DIFFERENT seed (new wallet instead of restore) fails GCM
 * auth on decrypt — surfaced as 'key-mismatch', never a silently empty cabinet.
 */
import { ref } from 'vue'
import { hkdf } from '@noble/hashes/hkdf.js'
import { sha256 } from '@noble/hashes/sha2.js'
import { useAuthStore } from '~/stores/auth'
import {
  readTipBatches, writeTipBatches, type TipBatch,
} from '~/composables/useTipBatches'
import {
  MAX_TX_ANNOTATION_ENTRIES, readTxAnnotations, writeTxAnnotations,
  type TxAnnotation,
} from '~/composables/useTxAnnotations'

interface SyncContainer {
  v: 1
  tipBatches: TipBatch[]
  txAnnotations: Record<string, TxAnnotation>
}

export type WalletSyncError = '' | 'key-mismatch' | 'network' | 'no-seed'

const API = '/api/v1/wallet-sync/'
const HKDF_INFO = 'parahub-wallet-sync-v1'
const UPLOAD_DEBOUNCE_MS = 3000
const PULL_MIN_INTERVAL_MS = 30_000

// Module-level: one sync state per tab, shared by every caller.
const enabled = ref<boolean | null>(null) // null = not fetched yet
const lastError = ref<WalletSyncError>('')
let cachedKey: { words: string, key: CryptoKey } | null = null
let uploadTimer: ReturnType<typeof setTimeout> | null = null
let lastPullAt = 0
let pullInflight: Promise<void> | null = null

// --- crypto ---

const deriveKey = async (): Promise<CryptoKey | null> => {
  const { loadSeed, mnemonicToSeed } = useSeed()
  const words = loadSeed()
  if (!words) return null
  const joined = words.join(' ')
  if (cachedKey && cachedKey.words === joined) return cachedKey.key
  const masterSeed = await mnemonicToSeed(words)
  const raw = hkdf(sha256, masterSeed, undefined, new TextEncoder().encode(HKDF_INFO), 32)
  const key = await crypto.subtle.importKey('raw', raw as Uint8Array<ArrayBuffer>, 'AES-GCM', false, ['encrypt', 'decrypt'])
  cachedKey = { words: joined, key }
  return key
}

const encrypt = async (key: CryptoKey, container: SyncContainer): Promise<string> => {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const plaintext = new TextEncoder().encode(JSON.stringify(container))
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext))
  const packed = new Uint8Array(iv.length + ct.length)
  packed.set(iv)
  packed.set(ct, iv.length)
  return btoa(String.fromCharCode(...packed))
}

/** Returns null when the ciphertext was made under a different seed (GCM auth failure). */
const decrypt = async (key: CryptoKey, blob: string): Promise<SyncContainer | null> => {
  try {
    const packed = Uint8Array.from(atob(blob), c => c.charCodeAt(0))
    const pt = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: packed.slice(0, 12) }, key, packed.slice(12))
    return JSON.parse(new TextDecoder().decode(pt)) as SyncContainer
  } catch {
    return null
  }
}

// --- merge ---

const mergeBatches = (local: TipBatch[], remote: TipBatch[]): TipBatch[] => {
  // Union by id; when both sides hold a batch, the later-edited copy wins
  // (notes are immutable after funding — only labels mutate).
  const byId = new Map<string, TipBatch>()
  for (const b of remote) byId.set(b.id, b)
  for (const b of local) {
    const other = byId.get(b.id)
    if (!other || (b.updatedAt ?? b.createdAt) >= (other.updatedAt ?? other.createdAt)) {
      byId.set(b.id, b)
    }
  }
  return [...byId.values()].sort((a, b) => b.createdAt - a.createdAt)
}

const mergeAnnotations = (
  local: Record<string, TxAnnotation>, remote: Record<string, TxAnnotation>,
): Record<string, TxAnnotation> => {
  // Annotations are write-once at send time, so any-write-wins is correct.
  const merged = { ...remote, ...local }
  const ids = Object.keys(merged)
  if (ids.length > MAX_TX_ANNOTATION_ENTRIES) {
    ids.sort((a, b) => (merged[a].ts || 0) - (merged[b].ts || 0))
    for (const id of ids.slice(0, ids.length - MAX_TX_ANNOTATION_ENTRIES)) delete merged[id]
  }
  return merged
}

// --- transport ---

const authedFetch = async <T>(method: 'GET' | 'PUT' | 'DELETE', body?: unknown): Promise<T> => {
  const authStore = useAuthStore()
  await authStore.ensureToken()
  return $fetch<T>(API, {
    method,
    body,
    credentials: 'include',
    headers: { Authorization: `Bearer ${authStore.token}` },
  })
}

interface SyncStateOut { enabled: boolean, ciphertext: string | null, updated_at: string | null }

const readLocalContainer = (): SyncContainer => ({
  v: 1,
  tipBatches: readTipBatches(),
  txAnnotations: readTxAnnotations(),
})

export const useWalletSync = () => {
  const authStore = useAuthStore()

  const canSync = () => import.meta.client && authStore.isAuthenticated

  /** Fetch the enabled flag (no merge). Cheap enough to call from settings UI. */
  const refreshStatus = async () => {
    if (!canSync()) return
    try {
      const out = await authedFetch<SyncStateOut>('GET')
      enabled.value = out.enabled
    } catch {
      lastError.value = 'network'
    }
  }

  const uploadNow = async () => {
    if (!canSync()) return
    // A send flow can annotate before anything fetched the flag this session.
    if (enabled.value === null) await refreshStatus()
    if (enabled.value !== true) return
    const key = await deriveKey()
    if (!key) return // no wallet on this device — nothing to contribute
    try {
      const ciphertext = await encrypt(key, readLocalContainer())
      await authedFetch<SyncStateOut>('PUT', { ciphertext })
      lastError.value = ''
    } catch {
      lastError.value = 'network'
    }
  }

  /**
   * Debounced upload — call after any local store write. Ads rail C can write
   * many annotations in a burst; one PUT at the end covers them all.
   */
  const scheduleUpload = () => {
    // Skip only when known-disabled; an unknown flag is resolved inside uploadNow.
    if (!import.meta.client || enabled.value === false) return
    if (uploadTimer) clearTimeout(uploadTimer)
    uploadTimer = setTimeout(() => { uploadTimer = null; uploadNow() }, UPLOAD_DEBOUNCE_MS)
  }

  /**
   * Download, decrypt, merge into localStorage, and push the merged state back
   * when this device held anything the blob lacked. Callers re-read the stores
   * afterwards. Throttled; `force` bypasses the throttle (toggle page).
   */
  const pull = async (force = false) => {
    if (!canSync()) return
    if (pullInflight) return pullInflight
    if (!force && Date.now() - lastPullAt < PULL_MIN_INTERVAL_MS) return
    pullInflight = (async () => {
      try {
        const out = await authedFetch<SyncStateOut>('GET')
        enabled.value = out.enabled
        lastPullAt = Date.now()
        if (!out.enabled || !out.ciphertext) return
        const key = await deriveKey()
        if (!key) { lastError.value = 'no-seed'; return }
        const remote = await decrypt(key, out.ciphertext)
        if (!remote) { lastError.value = 'key-mismatch'; return }
        lastError.value = ''
        const mergedBatches = mergeBatches(readTipBatches(), remote.tipBatches || [])
        const mergedAnns = mergeAnnotations(readTxAnnotations(), remote.txAnnotations || {})
        writeTipBatches(mergedBatches)
        writeTxAnnotations(mergedAnns)
        // Converge: if local knew something the blob didn't, share it back.
        const merged: SyncContainer = { v: 1, tipBatches: mergedBatches, txAnnotations: mergedAnns }
        if (JSON.stringify(merged) !== JSON.stringify({ v: 1, tipBatches: remote.tipBatches || [], txAnnotations: remote.txAnnotations || {} })) {
          const ciphertext = await encrypt(key, merged)
          await authedFetch<SyncStateOut>('PUT', { ciphertext })
        }
      } catch {
        lastError.value = 'network'
      } finally {
        pullInflight = null
      }
    })()
    return pullInflight
  }

  /** Turn sync on: uploads the current local stores as the first blob. */
  const enable = async (): Promise<boolean> => {
    if (!canSync()) return false
    const key = await deriveKey()
    if (!key) { lastError.value = 'no-seed'; return false }
    try {
      const ciphertext = await encrypt(key, readLocalContainer())
      const out = await authedFetch<SyncStateOut>('PUT', { ciphertext })
      enabled.value = out.enabled
      lastError.value = ''
      return true
    } catch {
      lastError.value = 'network'
      return false
    }
  }

  /** Turn sync off: the server forgets the ciphertext entirely. */
  const disable = async (): Promise<boolean> => {
    if (!canSync()) return false
    try {
      await authedFetch<SyncStateOut>('DELETE')
      enabled.value = false
      lastError.value = ''
      return true
    } catch {
      lastError.value = 'network'
      return false
    }
  }

  const hasWallet = () => import.meta.client && useSeed().hasSeed()

  return { enabled, lastError, hasWallet, refreshStatus, pull, scheduleUpload, uploadNow, enable, disable }
}
