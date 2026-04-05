from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from identity.models import Profile

Account = get_user_model()


class HNAAuthenticationBackend(ModelBackend):
    """
    Custom authentication backend that allows login with HNA (Human-Navigable Alias).
    Supports both email/password and HNA/password authentication.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('email')
        
        if username is None or password is None:
            return None
        
        # Check if username looks like an HNA (contains @)
        if '@' in username:
            # Could be either email or HNA
            # First try as email (which could be the HNA)
            try:
                user = Account.objects.get(email=username)
                if user.check_password(password):
                    return user
            except Account.DoesNotExist:
                pass
            
            # Try to find by HNA through Profile
            try:
                # Split HNA into local_name and domain
                local_name, domain = username.rsplit('@', 1)
                profile = Profile.objects.select_related('account').get(
                    local_name=local_name,
                    instance__domain=domain
                )
                user = profile.account
                if user.check_password(password):
                    return user
            except (Profile.DoesNotExist, ValueError):
                pass
        else:
            # Try as username
            try:
                user = Account.objects.get(username=username)
                if user.check_password(password):
                    return user
            except Account.DoesNotExist:
                pass
        
        return None
    
    def get_user(self, user_id):
        try:
            return Account.objects.get(pk=user_id)
        except Account.DoesNotExist:
            return None