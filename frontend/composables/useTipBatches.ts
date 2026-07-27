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
  sats: number
  expirySecs: number
  message: string
  /** Fiat face value and rate frozen at mint time — printed on the note. */
  fiat: string
  rate: string
  notes: TipBatchNote[]
}

const STORAGE_KEY = 'parahub_tip_batches'

const read = (): TipBatch[] => {
  if (!process.client) return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) as TipBatch[] : []
  } catch {
    return []
  }
}

const write = (batches: TipBatch[]) => {
  if (!process.client) return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(batches))
}

export const useTipBatches = () => {
  const batches = useState<TipBatch[]>('tip-batches', () => [])

  const load = () => { batches.value = read() }

  const get = (id: string): TipBatch | undefined =>
    (batches.value.length ? batches.value : read()).find(b => b.id === id)

  const save = (batch: TipBatch) => {
    const all = read()
    const i = all.findIndex(b => b.id === batch.id)
    if (i >= 0) all[i] = batch
    else all.unshift(batch)
    write(all)
    batches.value = all
  }

  const remove = (id: string) => {
    const all = read().filter(b => b.id !== id)
    write(all)
    batches.value = all
  }

  return { batches, load, get, save, remove }
}
