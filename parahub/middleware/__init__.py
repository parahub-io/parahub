"""
Middleware for Parahub
"""


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
