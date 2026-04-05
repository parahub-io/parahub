"""
Matrix SSO auto-login endpoint for Element
Creates Matrix user and redirects to Element with SSO
"""

from ninja import Router
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
import httpx
import hashlib
from django.conf import settings
from parahub.endpoints.matrix_auth import get_matrix_localpart_for_account

from parahub.ratelimit import ratelimit

router = Router(tags=["matrix-sso"])

SYNAPSE_BASE_URL = "http://localhost:8008"
SYNAPSE_PUBLIC_URL = "https://parahub.io"
SYNAPSE_ADMIN_TOKEN = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)
SYNAPSE_SHARED_SECRET = settings.SYNAPSE_REGISTRATION_SHARED_SECRET


@router.get("/element-login")
@ratelimit(group='matrix:element_login', key='ip', rate='10/m')
def element_auto_login(request):
    """
    Auto-login endpoint for Element
    Checks if user is authenticated, creates Matrix session, redirects to Element
    """
    # Check if user is authenticated
    if not request.user.is_authenticated:
        # Redirect to login with return URL
        return HttpResponseRedirect(f'/login/?next=/api/v1/matrix-sso/element-login')

    user = request.user

    # Generate Matrix user ID from profile's local_name (human-readable)
    matrix_localpart = get_matrix_localpart_for_account(user.id)
    matrix_user_id = f"@{matrix_localpart}:parahub.io"

    try:
        with httpx.Client() as client:
            # Generate deterministic password
            password = hashlib.sha256(f"{user.id}:{SYNAPSE_SHARED_SECRET}".encode()).hexdigest()

            # Try to login to Matrix (will create user if not exists via OIDC)
            login_data = {
                "type": "m.login.password",
                "user": matrix_localpart,
                "password": password,
                "initial_device_display_name": "Parahub Element"
            }

            login_response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/login",
                json=login_data
            )

            if login_response.status_code == 200:
                # Login successful - redirect to Element homepage (inside iframe)
                return HttpResponseRedirect('/element/#/home')
            else:
                # User doesn't exist - trigger SSO flow
                # Redirect to Matrix SSO which will create account via OIDC
                # After SSO, redirect to Element app (not /chat page)
                sso_url = f"{SYNAPSE_PUBLIC_URL}/_matrix/client/r0/login/sso/redirect/oidc-parahub_django?redirectUrl={SYNAPSE_PUBLIC_URL}/element/%23/home"
                return HttpResponseRedirect(sso_url)

    except Exception as e:
        # On any error, redirect to Matrix SSO
        sso_url = f"{SYNAPSE_PUBLIC_URL}/_matrix/client/r0/login/sso/redirect/oidc-parahub_django?redirectUrl={SYNAPSE_PUBLIC_URL}/element/%23/home"
        return HttpResponseRedirect(sso_url)
