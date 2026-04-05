"""
OIDC Provider implementation for Matrix Synapse integration
Maps Parahub ULID/HNA identities to OIDC claims
"""

from typing import Dict, Any
from oauth2_provider.models import Application
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class ParahubOIDCProvider:
    """
    Custom OIDC claims provider for Parahub identity system
    """
    
    @staticmethod
    def get_oidc_claims(user: User) -> Dict[str, Any]:
        """
        Generate OIDC claims for a Parahub user
        Maps ULID/HNA to standard OIDC claims plus custom claims for Synapse
        """
        profile = getattr(user, 'profile', None)
        
        claims = {
            # Standard OIDC claims
            'sub': user.id,  # Subject - use ULID as unique identifier
            'name': profile.display_name if profile else user.username,
            'preferred_username': user.username,
            'email': user.email,
            'email_verified': user.is_verified if hasattr(user, 'is_verified') else False,
            
            # Custom Parahub claims for Synapse mapping
            'id': user.id,
            'hna': user.hna if hasattr(user, 'hna') else f"{user.username}@parahub.io",
            'is_verified': user.is_verified if hasattr(user, 'is_verified') else False,
            'pgp_key_id': profile.pgp_key_id if profile and hasattr(profile, 'pgp_key_id') else None,
            
            # Additional profile data
            'picture': profile.avatar_url if profile and hasattr(profile, 'avatar_url') else None,
            'locale': profile.language if profile and hasattr(profile, 'language') else 'en',
            'updated_at': user.date_joined.timestamp() if hasattr(user, 'date_joined') else None,
        }
        
        # Remove None values
        return {k: v for k, v in claims.items() if v is not None}
    
    @staticmethod
    def get_userinfo_claims(user: User, scope: str) -> Dict[str, Any]:
        """
        Get claims based on requested scope
        """
        claims = {'sub': user.id}
        
        scopes = scope.split()
        
        if 'profile' in scopes:
            profile_claims = ParahubOIDCProvider.get_oidc_claims(user)
            claims.update({
                'name': profile_claims.get('name'),
                'preferred_username': profile_claims.get('preferred_username'),
                'picture': profile_claims.get('picture'),
                'locale': profile_claims.get('locale'),
                'id': profile_claims.get('id'),
                'hna': profile_claims.get('hna'),
            })
        
        if 'email' in scopes:
            claims.update({
                'email': user.email,
                'email_verified': user.is_verified if hasattr(user, 'is_verified') else False,
            })
        
        # Always include Parahub-specific claims for Synapse
        claims.update({
            'id': user.id,
            'hna': user.hna if hasattr(user, 'hna') else f"{user.username}@parahub.io",
        })
        
        # Remove None values
        return {k: v for k, v in claims.items() if v is not None}


def create_synapse_oidc_application():
    """
    Create or update the OIDC application for Synapse
    This should be called from a Django management command or migration
    """
    import os
    import secrets
    from oauth2_provider.models import Application

    # Get client secret from environment or generate a secure one
    client_secret = os.getenv('SYNAPSE_OIDC_CLIENT_SECRET')
    if not client_secret:
        client_secret = secrets.token_urlsafe(32)
        logger.warning("SYNAPSE_OIDC_CLIENT_SECRET not set in environment.")
        logger.warning(f"Generated new secret. Add to .env: SYNAPSE_OIDC_CLIENT_SECRET={client_secret}")

    app, created = Application.objects.update_or_create(
        client_id='synapse-client',
        defaults={
            'name': 'Matrix Synapse',
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_AUTHORIZATION_CODE,
            'client_secret': client_secret,
            'redirect_uris': 'https://parahub.io/_synapse/client/oidc/callback',
            'algorithm': Application.HS256_ALGORITHM,
            'skip_authorization': True,  # Auto-approve for internal service
        }
    )

    action = 'Created' if created else 'Updated'
    logger.info(f"{action} OIDC application for Synapse: {app.client_id}")
    return app


# OIDC Discovery endpoints configuration
OIDC_DISCOVERY = {
    'issuer': 'https://parahub.io',
    'authorization_endpoint': 'https://parahub.io/o/authorize/',
    'token_endpoint': 'https://parahub.io/o/token/',
    'userinfo_endpoint': 'https://parahub.io/o/userinfo/',
    'jwks_uri': 'https://parahub.io/.well-known/jwks.json',
    'response_types_supported': ['code', 'token', 'id_token', 'code token', 'code id_token', 'token id_token', 'code token id_token'],
    'subject_types_supported': ['public'],
    'id_token_signing_alg_values_supported': ['RS256', 'HS256'],
    'scopes_supported': ['openid', 'profile', 'email'],
    'token_endpoint_auth_methods_supported': ['client_secret_post', 'client_secret_basic'],
    'claims_supported': [
        'sub', 'name', 'preferred_username', 'email', 'email_verified',
        'id', 'hna', 'is_verified', 'pgp_key_id', 'picture', 'locale', 'updated_at'
    ],
    'code_challenge_methods_supported': ['plain', 'S256'],
}