"""
Custom OAuth2 Validator for OIDC userinfo support
"""
from oauth2_provider.oauth2_validators import OAuth2Validator
from django.contrib.auth import get_user_model
from django.conf import settings
from .settings import oidc_userinfo
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class CustomOAuth2Validator(OAuth2Validator):
    """
    Custom OAuth2 validator that properly handles OIDC userinfo requests
    """

    def get_userinfo_claims(self, request):
        """
        Override to provide custom userinfo claims including groups
        """
        user = request.user
        if not user or not user.is_authenticated:
            return {}

        # Get base claims
        claims = {}

        # Use our custom oidc_userinfo function
        try:
            claims = oidc_userinfo(claims, user)
            logger.info(f"Generated userinfo claims for user {user.username}: {claims.keys()}")
        except Exception as e:
            logger.error(f"Error generating userinfo claims: {e}")
            # Fallback to basic claims
            claims = {
                'sub': getattr(user, 'cri', str(user.id)),
                'email': user.email,
                'preferred_username': user.username,
                'groups': ['parahub-users']  # Always include at least one group
            }

        return claims

    def get_additional_claims(self, request):
        """
        Return additional claims for the userinfo endpoint and ID token
        """
        return self.get_userinfo_claims(request)

    def get_oidc_issuer_endpoint(self, request):
        """
        Override to provide correct OIDC issuer endpoint
        This is used by django-oauth-toolkit 3.x for ID token generation
        """
        issuer = settings.OAUTH2_PROVIDER.get('OIDC_ISSUER', 'https://parahub.io')
        logger.info(f"OIDC issuer endpoint: {issuer}")
        return issuer

    def get_id_token_dictionary(self, token, token_handler, request):
        """
        Override to set correct issuer in ID token for OIDC
        Note: django-oauth-toolkit 3.x uses get_id_token_dictionary, not get_id_token_dic
        Returns tuple: (claims_dict, expiration_time)
        """
        # Base class returns tuple (claims, expiration_time)
        id_token_dic, expiration_time = super().get_id_token_dictionary(token, token_handler, request)

        # Set issuer from settings (redundant with get_oidc_issuer_endpoint but ensures consistency)
        issuer = settings.OAUTH2_PROVIDER.get('OIDC_ISSUER', 'https://parahub.io')
        id_token_dic['iss'] = issuer

        # Add custom claims to ID token (for Synapse user mapping)
        user = request.user
        if user and user.is_authenticated:
            # Add account_id for Matrix localpart mapping (MUST be string, not list!)
            id_token_dic['account_id'] = str(user.id)  # Explicit str() to prevent list conversion

            # Add hna and local_name for display name and Matrix localpart
            try:
                from identity.models import Profile
                profile = Profile.objects.filter(account=user, is_publicly_linked=True).first()
                if profile:
                    id_token_dic['hna'] = str(profile.hna)  # Explicit str()
                    id_token_dic['local_name'] = str(profile.local_name)  # For Matrix localpart
                else:
                    id_token_dic['hna'] = str(user.email)  # Explicit str()
                    id_token_dic['local_name'] = str(user.username)  # Fallback
            except Exception:
                id_token_dic['hna'] = str(user.email)  # Explicit str()
                id_token_dic['local_name'] = str(user.username)  # Fallback

        logger.info(f"Generated ID token with issuer: {issuer}, account_id: {id_token_dic.get('account_id')} (type: {type(id_token_dic.get('account_id'))}), hna: {id_token_dic.get('hna')}")
        return id_token_dic, expiration_time