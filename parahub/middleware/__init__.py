"""
Middleware for Parahub
"""
import time


class SessionRenewalMiddleware:
    """
    Sliding session expiry with at most one django_session write per day.

    Replaces SESSION_SAVE_EVERY_REQUEST=True, which rewrote the session row
    (SELECT + UPDATE) on every request. Marking the session modified refreshes
    both the DB expiry and the cookie max-age, so an active user keeps a
    rolling 30-day window (worst case shortened by the renew interval).

    Must be listed AFTER SessionMiddleware so its response phase runs before
    the session is saved.
    """

    RENEW_INTERVAL = 24 * 3600

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = getattr(request, 'session', None)
        if session is not None and not session.is_empty():
            now = int(time.time())
            if now - session.get('_renewed_at', 0) > self.RENEW_INTERVAL:
                session['_renewed_at'] = now
        return response


class OAuthFrameMiddleware:
    """
    Allow OAuth/OIDC pages to be loaded in iframes from same origin.
    This is needed for Element Web SSO flow which runs in an iframe.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Allow OAuth/OIDC endpoints to be framed from same origin
        oauth_paths = ['/o/', '/_synapse/', '/accounts/']
        if any(request.path.startswith(path) for path in oauth_paths):
            # Remove restrictive frame-ancestors if present
            response['X-Frame-Options'] = 'SAMEORIGIN'

            # Update CSP to allow same-origin framing
            csp = response.get('Content-Security-Policy', '')
            if 'frame-ancestors' in csp:
                # Replace frame-ancestors 'none' with 'self'
                csp = csp.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
                response['Content-Security-Policy'] = csp

        return response
