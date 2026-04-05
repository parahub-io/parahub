"""
OIDC Provider settings for Parahub.
"""
from django.conf import settings
from identity.models import Profile, Account
from .models import RSAKeyPair
from oauth2_provider.scopes import BaseScopes
import logging

logger = logging.getLogger(__name__)


def oidc_userinfo(claims, user):
    """
    Populate userinfo response with custom claims based on Parahub user model.
    """
    try:
        # Get user's primary profile
        profile = Profile.objects.filter(account=user, is_publicly_linked=True).first()

        # Basic claims - CRITICAL: use Account.id for stable subject (Matrix compatibility)
        claims['sub'] = user.id  # Always use Account.id (immutable ULID)
        # Note: account_id is added in oauth_validators.py get_id_token_dictionary() for ID token
        claims['email'] = user.email
        
        # Check actual email verification status from allauth
        try:
            from allauth.account.models import EmailAddress
            email_address = EmailAddress.objects.filter(user=user, email=user.email, verified=True).first()
            claims['email_verified'] = bool(email_address)
        except Exception as e:
            logger.warning(f"Failed to check email verification status for user {user.id}: {e}")
            claims['email_verified'] = False  # Conservative default
        
        if profile:
            claims['preferred_username'] = profile.local_name  # Without domain — external services (PeerTube, Gitea) sanitize '@'
            # Note: hna added in oauth_validators.py get_id_token_dictionary() for ID token
            claims['name'] = profile.display_name or profile.local_name
            claims['profile'] = f"https://{profile.instance.domain}/profile/{profile.local_name}"

            # Parahub specific claims
            claims['parahub'] = {
                'id': profile.id,
                'object_type': 'profile',
                'hna': profile.hna,
                'local_name': profile.local_name,
                'reputation_score': float(profile.reputation_score),
                'is_verified_wot': profile.is_verified_wot,
                'instance': profile.instance.domain
            }
            
            # Groups claim for admin access (e.g., Traccar)
            groups = []
            if user.is_staff:
                groups.append('staff')
            if user.is_superuser:
                groups.append('admin')
                groups.append('traccar-admins')  # Traccar admin access
            
            # All authenticated Parahub users get basic access
            groups.append('parahub-users')
            
            # Check for establishment memberships
            memberships = profile.establishment_memberships.filter(role__in=['ADMIN', 'OWNER'])
            for membership in memberships:
                groups.append(f"org_{membership.establishment.slug or membership.establishment.id}_admin")
            
            if groups:
                claims['groups'] = groups
        else:
            claims['preferred_username'] = user.username
            # Note: hna added in oauth_validators.py get_id_token_dictionary() for ID token
            claims['name'] = user.get_full_name() or user.username
            
            # Always include groups even without profile
            groups = []
            if user.is_staff:
                groups.append('staff')
            if user.is_superuser:
                groups.append('admin')
                groups.append('traccar-admins')
            
            # Check Django groups
            user_groups = user.groups.all()
            for group in user_groups:
                groups.append(group.name)
            
            # All authenticated users get basic access
            if user.is_authenticated:
                groups.append('parahub-users')
            
            # Always return groups array (even if empty) to prevent NullPointerException
            claims['groups'] = list(set(groups))  # Remove duplicates
            
    except Exception as e:
        logger.error(f"Error generating OIDC claims for user {user.id}: {e}")
        # Fallback to basic claims using ULID for stable subject
        claims['sub'] = user.id  # Always use immutable ULID
        # Note: account_id and hna added in oauth_validators.py get_id_token_dictionary()
        claims['email'] = user.email
        claims['email_verified'] = False  # Conservative fallback
        claims['preferred_username'] = user.username
        claims['name'] = user.get_full_name() or user.username
        
        # Always include groups in fallback to prevent NullPointerException
        groups = []
        if user.is_staff:
            groups.append('staff')
        if user.is_superuser:
            groups.append('admin')
            groups.append('traccar-admins')
        for group in user.groups.all():
            groups.append(group.name)
        if user.is_authenticated:
            groups.append('parahub-users')
        claims['groups'] = list(set(groups))
        
    return claims


def oidc_subject_generator(user):
    """
    Generate subject identifier for OIDC tokens.
    CRITICAL: Always uses Account.id (not Profile.id) for Matrix/Synapse compatibility.
    Account.id is the stable, immutable identifier across the system.
    """
    # Always use Account.id - it's immutable and stable
    # DO NOT use Profile.id - users can have multiple profiles
    return user.id


# OIDC Provider configuration
OIDC_ISSUER = getattr(settings, 'OIDC_ISSUER', 'https://parahub.io')
OIDC_USERINFO = 'oidc_provider.settings.oidc_userinfo'
OIDC_SUBJECT_GENERATOR = 'oidc_provider.settings.oidc_subject_generator'

# Token settings
OIDC_ID_TOKEN_EXPIRE = 3600  # 1 hour
OIDC_ACCESS_TOKEN_EXPIRE = 3600  # 1 hour
OIDC_REFRESH_TOKEN_EXPIRE = 24 * 3600  # 24 hours

# Supported scopes
OIDC_SCOPES = [
    'openid',
    'profile',
    'email',
    'groups',
    'parahub'  # Custom scope for Parahub-specific claims
]

# Supported response types
OIDC_RESPONSE_TYPES = [
    'code',
    'id_token',
    'id_token token',
    'code id_token',
    'code token',
    'code id_token token'
]

# Supported grant types
OIDC_GRANT_TYPES = [
    'authorization_code',
    'implicit',
    'hybrid'
]


class CustomScopeClaims(BaseScopes):
    """
    Custom OIDC scope claims for Parahub
    """
    def get_available_scopes(self, application=None, request=None, *args, **kwargs):
        return [
            'openid',
            'profile',
            'email',
            'groups',
            'parahub',
            'read',
            'write'
        ]

    def get_default_scopes(self, application=None, request=None, *args, **kwargs):
        return ['openid', 'profile', 'email']

    def get_custom_claims(self, request, *args, **kwargs):
        """
        Generate custom claims for userinfo endpoint
        """
        user = request.user
        claims = {}
        
        # Always call our oidc_userinfo function to populate claims
        if user and user.is_authenticated:
            claims = oidc_userinfo(claims, user)
        
        return claims