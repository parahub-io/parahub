"""
OIDC Provider Views for Parahub
Implements OpenID Connect discovery and JWKS endpoints
"""

from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from jwcrypto import jwk
from .models import RSAKeyPair
import json
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
def openid_configuration(request):
    """
    OpenID Connect Discovery endpoint
    Returns the OpenID Provider configuration metadata
    """
    try:
        base_url = settings.OAUTH2_PROVIDER.get('OIDC_ISSUER', 'https://parahub.io')
        
        # Remove trailing slash
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        
        configuration = {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/o/authorize/",
            "token_endpoint": f"{base_url}/o/token/",
            "userinfo_endpoint": f"{base_url}/o/userinfo/",
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "end_session_endpoint": f"{base_url}/o/revoke_token/",
            
            # Supported scopes
            "scopes_supported": [
                "openid",
                "profile", 
                "email",
                "groups",
                "parahub"
            ],
            
            # Supported response types
            "response_types_supported": [
                "code",
                "id_token",
                "id_token token",
                "code id_token",
                "code token", 
                "code id_token token"
            ],
            
            # Supported grant types
            "grant_types_supported": [
                "authorization_code",
                "implicit",
                "refresh_token"
            ],
            
            # Supported response modes
            "response_modes_supported": [
                "query",
                "fragment",
                "form_post"
            ],
            
            # Subject types supported
            "subject_types_supported": ["public"],
            
            # ID Token signing algorithms supported
            "id_token_signing_alg_values_supported": ["RS256"],
            
            # UserInfo signing algorithms supported  
            "userinfo_signing_alg_values_supported": ["none"],
            
            # Token endpoint auth methods
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post"
            ],
            
            # Claims supported
            "claims_supported": [
                "sub",
                "name",
                "preferred_username",
                "email",
                "email_verified",
                "profile",
                "groups",
                "parahub"
            ],
            
            # Code challenge methods for PKCE
            "code_challenge_methods_supported": [
                "S256",
                "plain"
            ]
        }
        
        return JsonResponse(configuration)
        
    except Exception as e:
        logger.error(f"Error generating OpenID configuration: {e}")
        return JsonResponse(
            {"error": "server_error", "error_description": "Internal server error"},
            status=500
        )


@csrf_exempt
@require_http_methods(["GET"])
def jwks(request):
    """
    JSON Web Key Set (JWKS) endpoint
    Returns the public keys used for token signature verification
    """
    try:
        # Get all active RSA keys
        active_keys = RSAKeyPair.objects.filter(is_active=True)
        
        if not active_keys.exists():
            logger.warning("No active RSA keys found, generating new key")
            # Generate a new key if none exists
            key = RSAKeyPair.generate_keypair()
            active_keys = [key]
        
        keys = []
        
        for rsa_key in active_keys:
            try:
                # Convert RSA key to JWK format
                jwk_key = rsa_key.get_jwk()
                
                # Extract JWK components
                jwk_dict = json.loads(jwk_key.export())
                
                # Add required fields for OIDC
                jwk_dict.update({
                    "kid": str(rsa_key.kid),
                    "alg": "RS256",
                    "use": "sig"
                })
                
                keys.append(jwk_dict)
                
            except Exception as e:
                logger.error(f"Error converting RSA key {rsa_key.kid} to JWK: {e}")
                continue
        
        if not keys:
            logger.error("No valid keys could be exported for JWKS")
            return JsonResponse(
                {"error": "server_error", "error_description": "No valid signing keys available"},
                status=500
            )
        
        jwks_response = {
            "keys": keys
        }
        
        logger.info(f"Serving JWKS with {len(keys)} keys")
        return JsonResponse(jwks_response)
        
    except Exception as e:
        logger.error(f"Error generating JWKS: {e}")
        return JsonResponse(
            {"error": "server_error", "error_description": "Internal server error"},
            status=500
        )
