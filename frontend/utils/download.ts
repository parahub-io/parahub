import { isNative, getPlatform } from './capacitor'

/**
 * Hand a generated file to the user.
 *
 * On the web this is the usual `<a download>` click. That attribute is inert
 * inside the Capacitor WebView: the bridge installs no `DownloadListener`, and
 * a listener would not fire for `blob:` URLs anyway — the click is a silent
 * no-op, which is why every export button "did nothing" in the app. The native
 * path therefore writes the bytes to disk and opens the system share sheet,
 * which is where "Save to Files" / "Open with" / "Print" live.
 *
 * Android also keeps a copy in the public Documents folder, so the file stays
 * findable after the sheet is dismissed. iOS has no user-visible folder of its
 * own, so there the share sheet is the only handoff and the cache copy is
 * scratch.
 */
export async function saveFile(blob: Blob, filename: string): Promise<void> {
  const name = safeFilename(filename)
  if (isNative()) {
    try {
      await saveNative(blob, name)
      return
    } catch (err) {
      if (isShareDismissed(err)) return
      // A shell built before the Filesystem/Share plugins were added rejects
      // with "not implemented" — fall through to the anchor, which behaves
      // exactly as that shell did before.
      console.error('Native file save failed:', err)
    }
  }
  saveViaAnchor(blob, name)
}

/** Convenience wrapper for text the caller just built in memory. */
export function saveText(text: string, filename: string, mime = 'text/plain'): Promise<void> {
  return saveFile(new Blob([text], { type: mime }), filename)
}

function saveViaAnchor(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function saveNative(blob: Blob, filename: string) {
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import('@capacitor/filesystem'),
    import('@capacitor/share'),
  ])

  const data = await blobToBase64(blob)

  // Public Documents is writable without a permission prompt from Android 11
  // on (the app owns what it creates there) and the plugin runs a media scan
  // afterwards, so the file shows up in Files. Android 10 and older refuse it
  // under scoped storage unless the app opts into legacy storage, so the app
  // cache is the fallback — the share sheet still gets the file either way.
  const targets = getPlatform() === 'android'
    ? [Directory.Documents, Directory.Cache]
    : [Directory.Cache]

  let uri = ''
  let persisted = false
  for (const [i, directory] of targets.entries()) {
    try {
      ;({ uri } = await Filesystem.writeFile({ path: filename, data, directory, recursive: true }))
      persisted = directory === Directory.Documents
      break
    } catch (err) {
      if (i === targets.length - 1) throw err
    }
  }

  try {
    await Share.share({ title: filename, files: [uri] })
  } catch (err) {
    // A file already sitting in Documents is delivered even if the sheet never
    // opened. A cache copy is not, so that failure has to travel — dismissal
    // included, which the caller reads as "done" rather than an error.
    if (!persisted) throw err
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error)
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.slice(result.indexOf(',') + 1)) // drop the `data:...;base64,` prefix
    }
    reader.readAsDataURL(blob)
  })
}

/**
 * Dismissing the share sheet rejects the call ("Share canceled" on Android,
 * "Share canceled"/"Abort" on iOS). The file is already written, so this is a
 * completed save, not a failure — never fall back to the anchor for it.
 */
function isShareDismissed(err: unknown): boolean {
  const message = (err as { message?: string })?.message?.toLowerCase() ?? ''
  return message.includes('cancel') || message.includes('abort')
}

/** Keep a server-supplied filename from escaping the directory it is written to. */
function safeFilename(name: string): string {
  return name.replace(/[/\\]/g, '_').replace(/^\.+/, '') || 'download'
}
