// Cinny/Matrix browser-session helpers.
//
// Cinny v4.10.x keeps its Matrix session in localStorage (cinny_user_id,
// cinny_access_token, cinny_device_id, cinny_hs_base_url) and sync/crypto
// state in IndexedDB — fully independent from the Parahub Django session.
// Without an explicit wipe the session survives Parahub logout and account
// switches, so the chat would silently resume as the previous user.

/** Matrix user ID of the cached Cinny session (e.g. "@alice:parahub.io"), if any. */
export function getCinnySessionUserId(): string | null {
  if (process.server) return null
  return localStorage.getItem('cinny_user_id')
}

/**
 * Invalidate the cached Cinny device token on the homeserver (best-effort).
 * Must run BEFORE clearCinnyData() — the token is read from localStorage.
 * Server-side invalidation also stops Cinny instances syncing in other tabs.
 */
export async function logoutCinnySession(): Promise<void> {
  if (process.server) return
  const token = localStorage.getItem('cinny_access_token')
  if (!token) return
  try {
    await $fetch('/_matrix/client/v3/logout', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    })
  } catch {
    // Token already invalid or homeserver unreachable — the storage wipe
    // that follows is what detaches this browser from the session
  }
}

/**
 * Clear all Cinny/Matrix data (localStorage + IndexedDB).
 * IndexedDB deletion is blocked while a Cinny iframe holds connections —
 * destroy the iframe first when possible; leftovers trigger the device_id
 * recovery path in chat.vue on next mount.
 */
export async function clearCinnyData(): Promise<void> {
  if (process.server) return

  // Clear ALL localStorage (Cinny stores session data here)
  const keysToRemove: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    // Cinny and Matrix SDK use various prefixes
    if (key?.startsWith('cinny') || key?.startsWith('matrix') || key?.startsWith('mx_')) {
      keysToRemove.push(key)
    }
  }
  keysToRemove.forEach(key => {
    localStorage.removeItem(key)
  })

  // Get list of all IndexedDB databases and delete Matrix/Cinny related ones
  try {
    const databases = await indexedDB.databases()

    for (const db of databases) {
      // Delete all databases that might be Matrix/Cinny related
      if (db.name && (
        db.name.includes('matrix') ||
        db.name.includes('cinny') ||
        db.name.includes('crypto') ||
        db.name.startsWith('_matrix')
      )) {
        await new Promise((resolve) => {
          const req = indexedDB.deleteDatabase(db.name!)
          req.onsuccess = () => resolve(true)
          req.onerror = () => resolve(false)
          req.onblocked = () => resolve(false)
        })
      }
    }
  } catch (e) {
    // Fallback: try to delete known database names
    const knownDbs = ['cinny', 'matrix-js-sdk', 'matrix-js-sdk:crypto']
    for (const dbName of knownDbs) {
      try {
        await new Promise((resolve) => {
          const req = indexedDB.deleteDatabase(dbName)
          req.onsuccess = () => resolve(true)
          req.onerror = () => resolve(false)
          req.onblocked = () => resolve(false)
        })
      } catch (err) {
        // Ignore
      }
    }
  }
}
