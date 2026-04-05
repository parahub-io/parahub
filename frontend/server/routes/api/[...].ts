// Proxy all /api/** requests to Django backend
// Works in both dev and production builds
// NOTE: Use 127.0.0.1 instead of localhost to avoid IPv6 resolution issues
export default defineEventHandler(async (event) => {
  const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
  const path = event.path
  const target = `${backendUrl}${path}`

  return await proxyRequest(event, target, {
    // Forward cookies and headers for auth
    headers: {
      'X-Forwarded-Host': getRequestHost(event),
      'X-Forwarded-Proto': getRequestProtocol(event),
    },
  })
})
