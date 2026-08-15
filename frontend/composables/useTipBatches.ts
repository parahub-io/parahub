/**
 * Printed tip batches, stored client-side only.
 *
 * A batch holds the secrets of its notes, so it can never live on a server —
 * whoever holds a secret holds the money. localStorage is the whole database:
 * the sender needs it to reprint a sheet, and the per-note payment id lets the
 * batch read each note's real status straight from the wallet (waiting /
 * claimed / returned) instead of trusting a status we recorded ourselves.
 *
 * Losing this store does NOT lose the money: unclaimed notes come back to the
 * sender when their HTLC expires. It only loses the ability to reprint.
 *
 * Cross-device: users who opted into wallet sync (advanced preferences) carry
 * this store between devices as a seed-encrypted blob — see useWalletSync.
 * The server never sees plaintext; for everyone else the store stays local.
 */
export interface TipBatchNote {
  code: string
  paymentId?: string
  /** Set when funding this note failed, so a retry knows what to redo. */
  error?: string
  /** Sender's own label — which note went to whom. Never printed, never sent. */
  label?: string
}

export interface TipBatch {
  id: string
  createdAt: number
  /** Last local edit (labels) — lets sync merge pick the newer copy of a batch. */
  updatedAt?: number
  sats: number
  expirySecs: number
  message: string
  /** Fiat face value and rate frozen at mint time — printed on the note. */
  fiat: string
  rate: string
  notes: TipBatchNote[]
}

const STORAGE_KEY = 'parahub_tip_batches'
const DELETED_KEY = 'parahub_tip_deleted'
// Batch ids are minted once and never reused, so a tombstone can live forever;
// the cap only bounds the sync payload.
const MAX_TOMBSTONES = 200

/** Ids of locally deleted batches — tombstones so sync-merge cannot resurrect them. */
export const readTipTombstones = (): string[] => {
  if (!process.client) return []
  try {
    return JSON.parse(localStorage.getItem(DELETED_KEY) || '[]') as string[]
  } catch {
    return []
  }
}

export const writeTipTombstones = (ids: string[]) => {
  if (!process.client) return
  localStorage.setItem(DELETED_KEY, JSON.stringify(ids.slice(-MAX_TOMBSTONES)))
}

export const readTipBatches = (): TipBatch[] => {
  if (!process.client) return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) as TipBatch[] : []
  } catch {
    return []
  }
}

export const writeTipBatches = (batches: TipBatch[]) => {
  if (!process.client) return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(batches))
}

export const useTipBatches = () => {
  const batches = useState<TipBatch[]>('tip-batches', () => [])

  const load = () => { batches.value = readTipBatches() }

  const get = (id: string): TipBatch | undefined =>
    (batches.value.length ? batches.value : readTipBatches()).find(b => b.id === id)

  const save = (batch: TipBatch) => {
    batch.updatedAt = Date.now()
    const all = readTipBatches()
    const i = all.findIndex(b => b.id === batch.id)
    if (i >= 0) all[i] = batch
    else all.unshift(batch)
    writeTipBatches(all)
    batches.value = all
    useWalletSync().scheduleUpload()
  }

  const remove = (id: string) => {
    const all = readTipBatches().filter(b => b.id !== id)
    writeTipBatches(all)
    writeTipTombstones([...readTipTombstones(), id])
    batches.value = all
    useWalletSync().scheduleUpload()
  }

  return { batches, load, get, save, remove }
}
