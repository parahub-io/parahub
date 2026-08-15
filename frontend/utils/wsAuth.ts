/**
 * How a WebSocket authenticates itself, and the one place that knows where the
 * Android WebView differs.
 *
 * The JWT rides in a cookie, never in the URL: a query string ends up in every
 * nginx access log line, and a token is not something to leave there. The
 * Capacitor WebView has been seen not to attach that cookie to the upgrade
 * request at all (issue #465) — so a native client that the server refuses is
 * allowed exactly one retry with the token in the query string. That fallback
 * is a deliberate second best. A browser cannot set a header on a WebSocket
 * handshake, so the query string is the only channel left, and it is paid for
 * only on the devices where the cookie demonstrably did not arrive.
 */

import { isNative } from '~/utils/capacitor'

/** The close code every consumer answers an unauthenticated handshake with. */
export const WS_UNAUTHENTICATED = 4001

/**
 * `Lax`, not `Strict`. Both are same-site for a socket opened from our own
 * page, so `Lax` gives nothing away on the desktop — but `Strict` is what the
 * WebView was seen to withhold, and there is no reason to keep asking for it.
 */
export function setWsAuthCookie(token: string) {
  document.cookie = `ws_token=${token}; path=/; SameSite=Lax; Secure`
}

export function clearWsAuthCookie() {
  document.cookie = 'ws_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
}

/** Absolute ws(s) URL for a path, optionally carrying the token as a fallback. */
export function buildWsUrl(path: string, token?: string | null, withToken = false) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const query = withToken && token ? `?token=${encodeURIComponent(token)}` : ''
  return `${protocol}//${location.host}${path}${query}`
}

/**
 * Whether a close is worth one more attempt with the token in the URL.
 *
 * Only on a native build, only once, and only for the code that means "no
 * valid token was seen" — a refusal for any other reason is a refusal, and
 * retrying it in a reconnect loop would just hammer the server.
 */
export function shouldRetryWithToken(closeCode: number, alreadyRetried: boolean) {
  return closeCode === WS_UNAUTHENTICATED && !alreadyRetried && isNative()
}
