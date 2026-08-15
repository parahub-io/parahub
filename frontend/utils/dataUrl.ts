/**
 * Decode a `data:` URL into a Blob locally.
 *
 * `fetch(dataUrl).then(r => r.blob())` is the usual shortcut, but a fetch to a
 * `data:` URL is governed by the CSP `connect-src` directive, and ours lists
 * only `'self' blob:` — the browser blocks it with "Refused to connect" and the
 * caller sees a bare `TypeError: Failed to fetch`. Decoding in-process has no
 * such dependency (and no round-trip).
 */
export function dataUrlToBlob(dataUrl: string): Blob {
  const comma = dataUrl.indexOf(',')
  if (!dataUrl.startsWith('data:') || comma === -1) {
    throw new Error('Not a data URL')
  }

  const header = dataUrl.slice('data:'.length, comma)
  const payload = dataUrl.slice(comma + 1)
  const mime = header.split(';')[0] || 'application/octet-stream'

  if (!/;base64$/i.test(header)) {
    return new Blob([decodeURIComponent(payload)], { type: mime })
  }

  const binary = atob(payload)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}
