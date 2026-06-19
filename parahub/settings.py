"""
Django settings for parahub project.
"""

from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False)
)

# Read .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS', default='').split(',')

# CSRF settings
CSRF_TRUSTED_ORIGINS = env('CSRF_TRUSTED_ORIGINS', default='https://parahub.io').split(',')

# CORS settings
CORS_ALLOWED_ORIGINS = env('CORS_ALLOWED_ORIGINS', default='https://parahub.io').split(',')
CORS_ALLOW_CREDENTIALS = True

# Proxy/Reverse proxy settings for correct URL generation
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Site URL for absolute URLs (used when request context is unavailable)
SITE_URL = env('SITE_URL', default='https://parahub.io')
PARAHUB_SERVER_IP = env('PARAHUB_SERVER_IP', default='')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',

    # Third party apps
    'rest_framework',
    'corsheaders',
    'channels',
    'ninja_jwt.token_blacklist',  # JWT token blacklist for logout
    'constance',  # Dynamic settings (email, geo, timeouts)

    # Django Allauth
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.apple',

    # OAuth2/OIDC Provider
    'oauth2_provider',

    # Local apps
    'parahub',
    'core',
    'identity',
    'taxonomy',
    'market',
    'barter',
    'debts',
    'logistics',
    'geo',
    'governance',
    'iot',
    'finance',
    'ads',
    'psy',
    'currency',
    'oidc_provider',
    'audit_log',
    'notifications',
    'energy',
    'treasury',
    'agents',
    'tickets',
    'parasos',
    'cms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'parahub.middleware.OAuthFrameMiddleware',  # Allow OAuth pages in iframe
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'parahub.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'parahub.wsgi.application'

# ASGI Application for Channels
ASGI_APPLICATION = 'parahub.asgi.application'

# Redis
REDIS_HOST = env('REDIS_HOST', default='127.0.0.1')
REDIS_PORT = env.int('REDIS_PORT', default=6379)

# Channels (kept for ASGI routing, channels_redis removed)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': env.db()
}

# Добавляем ENGINE для PostGIS если используется PostgreSQL
if 'postgres' in DATABASES['default']['ENGINE']:
    DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'

# CONN_MAX_AGE=0 (close after each request) is safest for ASGI with multiple
# uvicorn instances (prod 4w + 4 dev 2w = 12 workers). Persistent connections
# accumulate per async context and exhaust max_connections=100.
# For connection reuse, deploy pgbouncer in front of PostgreSQL.
DATABASES['default']['CONN_MAX_AGE'] = 0
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# Custom User Model
AUTH_USER_MODEL = 'identity.Account'

# Cache Configuration (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://localhost:6379/1'),
        'KEY_PREFIX': 'parahub',
        'TIMEOUT': 3600,  # Default timeout 1 hour
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'ru-RU'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django Ninja JWT settings
from datetime import timedelta

NINJA_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': 'parahub.io',
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',  # Use id field from ULIDModel
    'USER_ID_CLAIM': 'user_id',
    
    'AUTH_TOKEN_CLASSES': ('ninja_jwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    
    'JTI_CLAIM': 'jti',
}

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': env('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}

# Security settings for production
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow iframe from same origin (Element on /chat)

# Session and CSRF cookie settings for OAuth
SESSION_COOKIE_NAME = 'sessionid'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'  # Allow OAuth redirects
SESSION_SAVE_EVERY_REQUEST = True  # Keep session alive

# CSRF settings
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_HTTPONLY = False  # Allow JS to read for AJAX requests
CSRF_COOKIE_SAMESITE = 'Lax'

# Django Sites Framework
SITE_ID = 1

# Django Allauth settings
AUTHENTICATION_BACKENDS = [
    'identity.backends.HNAAuthenticationBackend',  # Our custom HNA backend
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Allauth configuration (65.14+ API)
ACCOUNT_LOGIN_METHODS = {'email', 'username'}  # Allow both username and email
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'  # Use username field
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_LOGIN_ON_GET = True

# Custom adapters
ACCOUNT_ADAPTER = 'identity.adapters.AccountAdapter'
SOCIALACCOUNT_ADAPTER = 'identity.adapters.SocialAccountAdapter'

# After login redirect
LOGIN_REDIRECT_URL = '/'  # Изменено: редирект на главную после входа
LOGOUT_REDIRECT_URL = '/'

# Email Backend Settings
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = 'noreply@parahub.io'
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=25)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='noreply@parahub.io')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

# Mailcow Integration
MAILCOW_API_URL = env('MAILCOW_API_URL', default='http://127.0.0.1:8081')
MAILCOW_API_KEY = env('MAILCOW_API_KEY', default='')
MAILCOW_DOMAIN = env('MAILCOW_DOMAIN', default='parahub.io')
MAILCOW_DEFAULT_QUOTA_MB = env.int('MAILCOW_DEFAULT_QUOTA_MB', default=1024)

# Social Account Providers settings
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'FIELDS': [
            'id',
            'email',
            'name',
            'first_name',
            'last_name',
            'verified_email',
        ],
    },
    'apple': {
        'SCOPE': [
            'email',
            'name',
        ],
    }
}

# Traccar Integration Settings
TRACCAR_EMAIL_DOMAIN = env('TRACCAR_EMAIL_DOMAIN', default='parahub.io')
TRACCAR_DB_PASSWORD = env('TRACCAR_DB_PASSWORD')
TRACCAR_PUBLIC_HOST = env('TRACCAR_PUBLIC_HOST', default='')  # Public IP/hostname for GPS device config

# Mesh Network Settings
MESH_HEARTBEAT_KEY = env('MESH_HEARTBEAT_KEY', default='')
MESH_DEFAULT_OWNER_PROFILE_ID = env('MESH_DEFAULT_OWNER_PROFILE_ID', default='')
MESH_SSH_KEY_PATH = env('MESH_SSH_KEY_PATH', default=os.path.expanduser('~/.ssh/id_ed25519'))
MESH_SSH_TIMEOUT = 5
MESH_SUBSCRIPTION_PRICE_SATS = int(env('MESH_SUBSCRIPTION_PRICE_SATS', default='50000'))
MESH_SUBSCRIPTION_DURATION_DAYS = int(env('MESH_SUBSCRIPTION_DURATION_DAYS', default='30'))
MESH_LNBITS_URL = env('MESH_LNBITS_URL', default='')
MESH_LNBITS_INVOICE_KEY = env('MESH_LNBITS_INVOICE_KEY', default='')
MESH_VPS_WG_PUBKEY = env('MESH_VPS_WG_PUBKEY', default='')  # empty = VPS gateway disabled
MESH_VPS_WG_ENDPOINT = env('MESH_VPS_WG_ENDPOINT', default='')

# OAuth2/OIDC Provider Settings
OAUTH2_PROVIDER = {
    # OAuth2 settings
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
        'openid': 'OpenID Connect',
        'profile': 'Access to profile information',
        'email': 'Access to email address',
        'groups': 'Access to user groups',
        'parahub': 'Parahub-specific claims',
    },
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 24 * 60 * 60,  # 24 hours
    'AUTHORIZATION_CODE_EXPIRE_SECONDS': 600,
    
    # Disable PKCE requirement for legacy clients like Traccar
    'PKCE_REQUIRED': False,
    
    # OIDC settings
    'OIDC_ENABLED': True,
    'OIDC_ISSUER': env('OIDC_ISSUER', default='https://parahub.io'),
    'OIDC_ISS_ENDPOINT': env('OIDC_ISSUER', default='https://parahub.io'),  # Required for django-oauth-toolkit
    'OIDC_RSA_PRIVATE_KEY': open('/opt/parahub/oidc_rsa_key.pem', 'r').read() if os.path.exists('/opt/parahub/oidc_rsa_key.pem') else None,
    'OIDC_USERINFO': 'oidc_provider.settings.oidc_userinfo',
    'OIDC_SUBJECT_GENERATOR': 'oidc_provider.settings.oidc_subject_generator',
    'OIDC_ID_TOKEN_EXPIRE_SECONDS': 3600,
    'OIDC_EXTRA_SCOPE_CLAIMS': 'oidc_provider.settings.CustomScopeClaims',
    
    # Use our custom Application model if needed
    'APPLICATION_MODEL': 'oauth2_provider.Application',
    
    # Custom OAuth2 Validator
    'OAUTH2_VALIDATOR_CLASS': 'oidc_provider.oauth_validators.CustomOAuth2Validator',
}
# Matrix/Synapse Integration Settings
SYNAPSE_REGISTRATION_SHARED_SECRET = env('SYNAPSE_REGISTRATION_SHARED_SECRET')
SYNAPSE_ADMIN_USER = env('SYNAPSE_ADMIN_USER', default='admin')
SYNAPSE_ADMIN_TOKEN = env('SYNAPSE_ADMIN_TOKEN')

# Neo4j Graph Database Settings (for Barter Exchange Matching)
NEO4J_URI = env('NEO4J_URI', default='bolt://localhost:7687')
NEO4J_USER = env('NEO4J_USER', default='neo4j')
NEO4J_PASSWORD = env('NEO4J_PASSWORD')
NEO4J_DATABASE = env('NEO4J_DATABASE', default='neo4j')  # Default database
NEO4J_MAX_CONNECTION_LIFETIME = 3600  # 1 hour
NEO4J_MAX_CONNECTION_POOL_SIZE = 50
NEO4J_CONNECTION_ACQUISITION_TIMEOUT = 120.0  # seconds

# Audit Log Settings (Cryptographic Proofs)
AUDIT_LOG_GIT_PATH = BASE_DIR / 'audit-log'
AUDIT_LOG_PUBLIC_GIT_REMOTE = env('AUDIT_LOG_PUBLIC_GIT_REMOTE', default='')  # Optional: push to Gitea
OPENTIMESTAMPS_ENABLED = env('OPENTIMESTAMPS_ENABLED', default=True, cast=bool)

# CMS Git Mirror
CMS_GIT_ROOT = BASE_DIR / 'cms-repos'

# Federation Settings
FEDERATION_ENABLED = env('FEDERATION_ENABLED', default=False, cast=bool)
FEDERATION_DOMAIN = env('FEDERATION_DOMAIN', default='parahub.io')
FEDERATION_NODE_PGP_FINGERPRINT = env('FEDERATION_NODE_PGP_FINGERPRINT', default='')

# Jitsi Meet Settings
JITSI_JWT_SECRET = env('JITSI_JWT_SECRET', default=None)

# GeoIP2 for market country filtering
GEOIP_PATH = '/opt/parahub/geoip/'

# ============================================================================
# Django Constance - Dynamic Settings
# ============================================================================
# Universal settings storage for simple configs (email, geo, timeouts, etc.)
# Admin UI: /admin/constance/config/
# Complex settings (like AISettings with API keys) use dedicated models
#
# Usage in code:
#   from constance import config
#   radius = config.DEFAULT_SEARCH_RADIUS_KM

CONSTANCE_BACKEND = 'constance.backends.redisd.RedisBackend'
CONSTANCE_REDIS_CONNECTION = env('REDIS_URL', default='redis://localhost:6379/1')

CONSTANCE_CONFIG = {
    # Email Settings
    'EMAIL_HOST': ('localhost', 'SMTP server hostname', str),
    'EMAIL_PORT': (25, 'SMTP server port', int),
    'EMAIL_USE_TLS': (False, 'Use TLS for email', bool),
    'EMAIL_USE_SSL': (False, 'Use SSL for email', bool),
    'DEFAULT_FROM_EMAIL': ('noreply@parahub.io', 'Default sender email address', str),

    # Registration
    'REGISTRATION_ENABLED': (True, 'Allow direct email/password registration (disable = Google Sign In only)', bool),

    # Mailcow Integration
    'MAILCOW_ENABLED': (False, 'Enable automatic mailbox creation on registration', bool),
    'MAILCOW_DEFAULT_QUOTA_MB': (1024, 'Default mailbox quota in MB', int),

    # Geo / Search Settings
    'DEFAULT_SEARCH_RADIUS_KM': (5.0, 'Default search radius in kilometers', float),
    'FEATURES_AT_POINT_RADIUS_M': (50, 'Features-at-point search radius in meters', int),
    'GEOCODING_RADIUS_M': (5000, 'Geocoding search radius in meters (5km)', int),

    # Cache / Performance Settings
    'CACHE_TIMEOUT_SECONDS': (3600, 'Default cache timeout (1 hour)', int),

    # Neo4j Connection Settings
    'NEO4J_MAX_CONNECTION_LIFETIME': (3600, 'Neo4j connection lifetime in seconds (1 hour)', int),
    'NEO4J_MAX_CONNECTION_POOL_SIZE': (50, 'Neo4j max connection pool size', int),
    'NEO4J_CONNECTION_ACQUISITION_TIMEOUT': (120.0, 'Neo4j connection acquisition timeout in seconds', float),

    # OAuth2 / Session Settings
    'OAUTH2_ACCESS_TOKEN_EXPIRE_SECONDS': (3600, 'OAuth2 access token lifetime (1 hour)', int),
    'OAUTH2_REFRESH_TOKEN_EXPIRE_SECONDS': (86400, 'OAuth2 refresh token lifetime (24 hours)', int),
    'OAUTH2_AUTHORIZATION_CODE_EXPIRE_SECONDS': (600, 'OAuth2 authorization code lifetime (10 min)', int),
    'SESSION_COOKIE_AGE_SECONDS': (2592000, 'Session cookie age (30 days)', int),

    # WebSocket / Channels Settings
    'CHANNELS_CAPACITY': (1500, 'Channels layer capacity', int),
    'CHANNELS_EXPIRY_SECONDS': (10, 'Channels layer message expiry', int),

    # Barter
    'BARTER_MAX_CHAIN_LENGTH': (5, 'Maximum barter cycle chain length (2=direct, 3=triangular, etc). Higher values increase Neo4j query time significantly.', int),

    # Governance
    'GOVERNING_ASSOCIATION_SLUG': ('parahub-associacao', 'Slug of the Establishment that acts as the governing body of this instance (grants foundation member status)', str),

    # Association Income (addresses read from Establishment.spark_address/ln_address)
    'EGAC_FEE_PERCENT': (1.0, 'EGAC management fee percentage for energy billing', float),
}

CONSTANCE_CONFIG_FIELDSETS = {
    'Email Configuration': {
        'fields': ('EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_USE_TLS', 'EMAIL_USE_SSL', 'DEFAULT_FROM_EMAIL'),
        'collapse': False,
    },
    'Registration': {
        'fields': ('REGISTRATION_ENABLED',),
        'collapse': False,
    },
    'Mailcow Integration': {
        'fields': ('MAILCOW_ENABLED', 'MAILCOW_DEFAULT_QUOTA_MB'),
        'collapse': False,
    },
    'Geo & Search': {
        'fields': ('DEFAULT_SEARCH_RADIUS_KM', 'FEATURES_AT_POINT_RADIUS_M', 'GEOCODING_RADIUS_M'),
        'collapse': False,
    },
    'Performance & Caching': {
        'fields': ('CACHE_TIMEOUT_SECONDS', 'NEO4J_MAX_CONNECTION_LIFETIME',
                   'NEO4J_MAX_CONNECTION_POOL_SIZE', 'NEO4J_CONNECTION_ACQUISITION_TIMEOUT'),
        'collapse': True,
    },
    'OAuth2 & Sessions': {
        'fields': ('OAUTH2_ACCESS_TOKEN_EXPIRE_SECONDS', 'OAUTH2_REFRESH_TOKEN_EXPIRE_SECONDS',
                   'OAUTH2_AUTHORIZATION_CODE_EXPIRE_SECONDS', 'SESSION_COOKIE_AGE_SECONDS'),
        'collapse': True,
    },
    'WebSocket / Channels': {
        'fields': ('CHANNELS_CAPACITY', 'CHANNELS_EXPIRY_SECONDS'),
        'collapse': True,
    },
    'Barter': {
        'fields': ('BARTER_MAX_CHAIN_LENGTH',),
        'collapse': False,
    },
    'Governance': {
        'fields': ('GOVERNING_ASSOCIATION_SLUG',),
        'collapse': False,
    },
    'Association Income': {
        'fields': ('EGAC_FEE_PERCENT',),
        'collapse': False,
    },
}
