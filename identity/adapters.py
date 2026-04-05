from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.sites.shortcuts import get_current_site
from django.contrib import messages
from core.models import Instance
from identity.models import Profile
import logging
import secrets
import string

logger = logging.getLogger(__name__)


class AccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for ParaHub."""
    
    def save_user(self, request, user, form, commit=True):
        """Save user with instance assignment."""
        user = super().save_user(request, user, form, commit=False)
        
        # Get or create instance based on current site domain
        domain = get_current_site(request).domain
        instance, created = Instance.objects.get_or_create(
            domain=domain,
            defaults={
                'name': domain,
                'public_key': '',  # Will be generated later
                'is_active': True
            }
        )
        
        # Assign instance to user
        user.instance = instance
        
        if commit:
            user.save()
        
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter for ParaHub."""
    
    def is_auto_signup_allowed(self, request, sociallogin):
        """Allow automatic signup to skip confirmation page."""
        return True
    
    def populate_user(self, request, sociallogin, data):
        """Populate user instance from social account data."""
        user = super().populate_user(request, sociallogin, data)
        
        # For new users, we clear username/email because we generate a custom HNA.
        # For existing users, we must not touch these fields.
        if not user.pk:  # Only for new users
            # This prevents conflicts with our HNA generation logic
            user.username = None
            user.email = None
        
        return user
    
    def save_user(self, request, sociallogin, form=None):
        """Save user from social login with HNA and password generation."""
        user = sociallogin.user
        logger.info(f"[OAuth] Starting save_user for social login. User PK: {user.pk}, Provider: {sociallogin.account.provider}")
        
        # Get or create instance based on current site domain
        domain = get_current_site(request).domain
        instance, created = Instance.objects.get_or_create(
            domain=domain,
            defaults={
                'name': domain,
                'public_key': '',  # Will be generated later
                'is_active': True
            }
        )
        
        # Assign instance to user
        user.instance = instance

        # Check if this is truly a new user by checking if Profile exists
        # Note: user.pk may already be set by allauth, so we check Profile instead
        is_new_user = not Profile.objects.filter(account=user).exists()

        # Generate HNA (Human-Navigable Alias) if this is a new user
        if is_new_user:
            logger.info("[OAuth] Processing new user registration")

            # Import Matrix availability check
            try:
                from parahub.endpoints.auth import _check_username_available_in_matrix
            except ImportError:
                logger.warning("[OAuth] Could not import Matrix check, skipping Matrix validation")
                _check_username_available_in_matrix = lambda x: True  # Fallback: assume available

            # Try to import and use username generator with proper error handling
            local_name = None

            try:
                # Try primary method - import username generator
                from core.username_generator import generate_username, generate_secure_password, ADJECTIVES, NOUNS
                logger.info("[OAuth] Successfully imported username_generator module")

                # Generate username that's also available in Matrix
                max_attempts = 50
                for attempt in range(max_attempts):
                    candidate = generate_username()
                    if _check_username_available_in_matrix(candidate):
                        local_name = candidate
                        logger.info(f"[OAuth] Generated username (Matrix-verified): {local_name}")
                        break
                    else:
                        logger.debug(f"[OAuth] Username {candidate} taken in Matrix, trying another...")

                if not local_name:
                    # All attempts failed, use timestamp fallback
                    import time
                    local_name = f"user-{int(time.time() * 1000) % 1000000}"
                    logger.warning(f"[OAuth] All Matrix-check attempts failed, using timestamp: {local_name}")

            except ImportError as e:
                logger.error(f"[OAuth] Failed to import username_generator: {e}")
                logger.info("[OAuth] Falling back to secondary username generation")

            except Exception as e:
                logger.error(f"[OAuth] Error during username generation: {e}")
                logger.info("[OAuth] Falling back to secondary username generation")

            # Fallback username generation if primary failed
            if not local_name:
                logger.warning("[OAuth] Primary username generation failed, using fallback method")
                # Simple fallback that doesn't require external dependencies
                import random
                adjectives = ['happy', 'sunny', 'swift', 'bright', 'cool', 'smart', 'brave']
                nouns = ['fox', 'tiger', 'eagle', 'wolf', 'lion', 'star', 'moon']

                max_attempts = 50
                for attempt in range(max_attempts):
                    random_num = random.randint(100, 9999)
                    candidate = f"{random.choice(adjectives)}-{random.choice(nouns)}-{random_num}"
                    if _check_username_available_in_matrix(candidate):
                        local_name = candidate
                        break

                if not local_name:
                    import time
                    local_name = f"user-{int(time.time())}"

                logger.info(f"[OAuth] Generated fallback username: {local_name}")

            # Final safety check
            if not local_name:
                # Ultimate fallback - use timestamp
                import time
                local_name = f"user-{int(time.time())}"
                logger.error(f"[OAuth] All username generation methods failed, using timestamp: {local_name}")
            
            # Create full HNA
            hna = f"{local_name}@{domain}"
            logger.info(f"[OAuth] Setting username: {local_name}, HNA: {hna}")
            
            # Set username to local_name and email to HNA
            user.username = local_name
            user.email = hna
            
            # Generate secure password with fallback
            password = None
            try:
                # Try to use the imported function if available
                password = generate_secure_password(length=12)
                logger.info("[OAuth] Generated password using primary method")
            except (NameError, Exception) as e:
                logger.warning(f"[OAuth] Primary password generation failed: {e}, using fallback")
                # Fallback password generation
                chars = string.ascii_letters + string.digits + "!@#$%^&*"
                password = ''.join(secrets.choice(chars) for _ in range(12))
                logger.info("[OAuth] Generated password using fallback method")
            
            user.set_password(password)
            
            # Store credentials as user attributes - they will be copied to session
            # by user_logged_in signal handler (Django creates new session on login)
            user._oauth_generated_hna = hna
            user._oauth_generated_password = password
            user._oauth_is_new_user = True
            logger.info(f"[OAuth] Stored credentials on user object for post-login session copy")
            
            # Final validation before saving
            if not user.username or user.username.strip() == '':
                # Emergency fallback - this should never happen with our checks above
                import time
                user.username = f"emergency-user-{int(time.time())}"
                logger.error(f"[OAuth] CRITICAL: Username was empty after all checks! Set to: {user.username}")
            
            logger.info(f"[OAuth] Final user data before save - Username: {user.username}, Email: {user.email}")

            # Record registration IP
            xff = request.META.get('HTTP_X_FORWARDED_FOR')
            user.registration_ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')

            # Save the user first
            user.save()
            logger.info(f"[OAuth] User saved successfully with ID: {user.pk}")

            # Clear email_addresses to prevent allauth from overwriting our HNA
            # allauth's setup_user_email() would set user.email to Google email otherwise
            sociallogin.email_addresses = []

            # Save SocialAccount to link social login to user
            sociallogin.save(request)

            # Mark HNA email as verified so allauth skips verification email.
            # The HNA is our internal email — verification is meaningless,
            # and sending before Mailcow mailbox Thread finishes causes 500.
            EmailAddress.objects.update_or_create(
                user=user,
                email=hna,
                defaults={'verified': True, 'primary': True},
            )

            # Detect user's preferred language from cookie or Accept-Language header
            preferred_language = 'en'  # Default fallback

            # Try to get from cookie first
            lang_cookie = request.COOKIES.get('preferred_language')
            if lang_cookie and lang_cookie in ['en', 'es', 'fr', 'de', 'pt', 'ru']:
                preferred_language = lang_cookie
                logger.info(f"[OAuth] Detected language from cookie: {preferred_language}")
            else:
                # Fallback to Accept-Language header
                accept_lang = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
                if accept_lang:
                    # Parse Accept-Language header (e.g., "ru-RU,ru;q=0.9,en;q=0.8")
                    lang_code = accept_lang.split(',')[0].split('-')[0].lower()
                    if lang_code in ['en', 'es', 'fr', 'de', 'pt', 'ru']:
                        preferred_language = lang_code
                        logger.info(f"[OAuth] Detected language from Accept-Language header: {preferred_language}")

            # Create Profile for the user
            Profile.objects.create(
                account=user,
                instance=instance,
                local_name=local_name,
                display_name=sociallogin.account.extra_data.get('name', ''),
                preferred_language=preferred_language,
                is_primary=True
            )
            logger.info(f"[OAuth] Profile created for user {user.username} with language {preferred_language}")
            
            # Add a message for the user
            messages.success(
                request,
                f"Welcome! Your HNA is: {hna} and a password has been generated for you. "
                f"Please save your credentials securely."
            )
        else:
            # Existing user, just save
            user.save()
            logger.info(f"[OAuth] Existing user logged in: {user.username}")

            # Clear email_addresses to prevent allauth from overwriting our HNA
            sociallogin.email_addresses = []

            # Save SocialAccount if not already linked
            if not sociallogin.is_existing:
                sociallogin.save(request)

            # Sync language from cookie if profile language is empty
            try:
                profile = Profile.objects.filter(account=user).first()
                if profile and not profile.preferred_language:
                    lang_cookie = request.COOKIES.get('preferred_language')
                    if lang_cookie and lang_cookie in ['en', 'es', 'fr', 'de', 'pt', 'ru']:
                        profile.preferred_language = lang_cookie
                        profile.save(update_fields=['preferred_language'])
                        logger.info(f"[OAuth] Synced language from cookie for existing user: {lang_cookie}")
            except Exception as e:
                logger.error(f"[OAuth] Failed to sync language for existing user: {e}")

        return user