/**
 * `WIFI:` join payload — the de-facto QR format every phone camera understands.
 *
 * `\` `;` `,` `:` and `"` are the format's own separators, so a credential
 * containing one has to arrive escaped or the scanner truncates the field.
 * Private WiFi is sae-mixed (WPA2+WPA3); `WPA` is the token both accept.
 */
export function wifiJoinPayload(ssid: string, password: string): string {
  const esc = (s: string) => s.replace(/([\\;,:"])/g, '\\$1')
  return `WIFI:T:WPA;S:${esc(ssid)};P:${esc(password)};;`
}
