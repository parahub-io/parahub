"""
No models. This app carries the OIDC hooks for django-oauth-toolkit
(settings.py: userinfo/subject/scope claims, oauth_validators.py) and the
create_*_oidc_app management commands. The actual endpoints live under /o/
(oauth2_provider.urls) and /oauth/ (identity.urls_oidc).
"""
