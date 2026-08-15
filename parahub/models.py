"""
Parahub core models
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AISettings(models.Model):
    """
    Global AI settings (singleton model - only one instance).
    Configurable via Django admin.

    Holds the vision-analysis config (enabled/provider/categorization) AND the
    platform-wide AI API keys: zenith_service (global-key fallback),
    support_voice, CMS illustration generation, profile photo checks and the
    image-generation scripts all read their keys from this model.
    """

    # Labels carry no prices and no model version: both go stale the moment a
    # tier is repointed, and a stale price on the control you pick a provider
    # with is worse than none. The admin renders each option with the model id
    # and rate it actually bills, read from `services/ai_pricing` at form time.
    class Provider(models.TextChoices):
        HAIKU = 'haiku', 'Claude Haiku'
        GPT5_MINI = 'gpt-5-mini', 'GPT-5 mini'
        GPT5_NANO = 'gpt-5-nano', 'GPT-5 nano'
        GEMINI_FLASH = 'gemini-flash', 'Gemini Flash'
        GEMINI_FLASH_LITE = 'gemini-flash-lite', 'Gemini Flash-Lite'

    class CategorizationProvider(models.TextChoices):
        HAIKU = 'haiku', 'Claude Haiku'
        GPT5_NANO = 'gpt-5-nano', 'GPT-5 nano'
        GPT5_MINI = 'gpt-5-mini', 'GPT-5 mini'
        GEMINI_FLASH = 'gemini-flash', 'Gemini Flash'
        GEMINI_FLASH_LITE = 'gemini-flash-lite', 'Gemini Flash-Lite'
        SAME = 'same', 'Same as vision provider'

    enabled = models.BooleanField(
        default=False,
        help_text="Enable AI-powered image analysis for marketplace items"
    )

    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.GEMINI_FLASH_LITE,
        help_text="AI provider to use for image analysis (vision + description)"
    )

    categorization_provider = models.CharField(
        max_length=20,
        choices=CategorizationProvider.choices,
        default=CategorizationProvider.HAIKU,
        help_text="AI provider for category selection (uses cheaper models, sees ALL categories)"
    )

    use_single_request = models.BooleanField(
        default=False,
        verbose_name="Use single request",
        help_text="When vision and categorization use same provider, combine into ONE request instead of two. Faster (~8s vs 13s). Supported: Claude, OpenAI, Gemini."
    )

    market_discount_pct = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal('0.20'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('1'))],
        help_text=(
            "Liquidity discount applied to the AI-suggested market price before it is "
            "pre-filled into the listing form. 0.20 = anchor the asking price 20% below "
            "the model's raw estimate to favour faster sales; 0 = disabled. The seller can "
            "always edit the final price."
        )
    )

    # API Keys (encrypted in production)
    claude_api_key = models.CharField(
        max_length=200,
        blank=True,
        help_text="Anthropic API key for Claude Sonnet 4.5 (sk-ant-...)"
    )

    openai_api_key = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="OpenAI API key",
        help_text="For GPT-5 models (sk-...)"
    )

    google_api_key = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Google Gemini API key",
        help_text="For Gemini Flash (vision & categorization). Get from https://aistudio.google.com/apikey (format: AIza...)"
    )

    # Usage stats
    total_requests = models.IntegerField(
        default=0,
        help_text="Total number of AI analysis requests"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Settings"
        verbose_name_plural = "AI Settings"

    def __str__(self):
        return f"AI Settings ({self.get_provider_display()}) - {'Enabled' if self.enabled else 'Disabled'}"

    def save(self, *args, **kwargs):
        # Singleton pattern - delete other instances
        if not self.pk and AISettings.objects.exists():
            AISettings.objects.all().delete()
        return super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """Get the singleton instance (create a disabled default if none exists).

        Reads the oldest row exactly like the `.objects.first()` consumers do,
        instead of get_or_create(pk=1): if the singleton was ever recreated
        under a different pk, the pk=1 variant would spawn a second blank row
        and every reader would silently switch to the unconfigured copy.
        """
        instance = cls.objects.first()
        if instance is None:
            instance = cls.objects.create()
        return instance


class AIAnalysisLog(models.Model):
    """
    Log of AI vision analysis requests for monitoring and quality tracking
    """
    from identity.models import Profile
    from market.models import Item
    from taxonomy.models import Category

    # Request info
    profile = models.ForeignKey('identity.Profile', on_delete=models.SET_NULL, null=True, related_name='ai_analyses')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Image info
    image_filename = models.CharField(max_length=255, blank=True)
    image_size_original = models.IntegerField(help_text="Original image size in bytes")
    image_size_compressed = models.IntegerField(help_text="Compressed image size in bytes")

    # AI providers (two-step process)
    vision_provider = models.CharField(max_length=20, default='unknown', help_text="Provider for vision analysis (claude, openai, google)")
    categorization_provider = models.CharField(max_length=20, default='unknown', help_text="Provider for categorization (haiku, gpt-5-nano, etc.)")

    # User language (for generated content)
    language = models.CharField(max_length=10, default='en', help_text="User's preferred language code (en, ru, pt, etc.)")

    # AI suggestions
    suggested_category = models.ForeignKey('taxonomy.Category', on_delete=models.SET_NULL, null=True, blank=True)
    suggested_category_confidence = models.FloatField(default=0.0)
    suggested_title = models.TextField(blank=True)
    suggested_description = models.TextField(blank=True)
    suggested_price = models.JSONField(null=True, blank=True, help_text="Pricing option suggested by AI")
    overall_confidence = models.FloatField(default=0.0)

    # Performance (separate for each step)
    vision_processing_time_ms = models.IntegerField(null=True, blank=True, help_text="Vision analysis time in milliseconds")
    categorization_processing_time_ms = models.IntegerField(null=True, blank=True, help_text="Categorization time in milliseconds")
    processing_time_ms = models.IntegerField(help_text="Total time taken for AI analysis in milliseconds (legacy)")

    # Usage tracking - Vision request (step 1: image → title/description)
    vision_input_tokens = models.IntegerField(null=True, blank=True, help_text="Vision: input tokens")
    vision_output_tokens = models.IntegerField(null=True, blank=True, help_text="Vision: output tokens")
    vision_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, help_text="Vision: API cost")

    # Usage tracking - Categorization request (step 2: text → category)
    categorization_input_tokens = models.IntegerField(null=True, blank=True, help_text="Categorization: input tokens")
    categorization_output_tokens = models.IntegerField(null=True, blank=True, help_text="Categorization: output tokens")
    categorization_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, help_text="Categorization: API cost")

    # Legacy fields (for backward compatibility, will be removed later)
    input_tokens = models.IntegerField(null=True, blank=True, help_text="DEPRECATED: Use vision_input_tokens")
    output_tokens = models.IntegerField(null=True, blank=True, help_text="DEPRECATED: Use vision_output_tokens")
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, help_text="DEPRECATED: Use vision_cost_usd + categorization_cost_usd")

    # Error tracking
    error_message = models.TextField(blank=True, help_text="Error message if analysis failed")

    # Raw request/response data (for debugging and transparency)
    vision_request_prompt = models.TextField(blank=True, help_text="Full prompt sent to vision AI (for debugging)")
    vision_response_raw = models.TextField(blank=True, help_text="Raw JSON response from vision AI")
    categorization_request_prompt = models.TextField(blank=True, help_text="Full prompt sent to categorization AI")
    categorization_response_raw = models.TextField(blank=True, help_text="Raw JSON response from categorization AI")

    # Outcome tracking (for accuracy monitoring)
    final_item = models.ForeignKey('market.Item', on_delete=models.SET_NULL, null=True, blank=True,
                                   help_text="Item created after this analysis (if any)")
    user_accepted_category = models.BooleanField(null=True, blank=True,
                                                  help_text="Did user keep the suggested category?")
    user_accepted_title = models.BooleanField(null=True, blank=True,
                                               help_text="Did user keep the suggested title?")
    user_accepted_price = models.BooleanField(null=True, blank=True,
                                               help_text="Did user keep the suggested price?")

    class Meta:
        verbose_name = "AI Analysis Log"
        verbose_name_plural = "AI Analysis Logs"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['vision_provider', '-created_at']),
            models.Index(fields=['profile', '-created_at']),
        ]

    def __str__(self):
        return f"AI Analysis by {self.profile.hna if self.profile else 'Unknown'} ({self.vision_provider}) - {self.created_at}"

    @property
    def accuracy_score(self):
        """Calculate accuracy score based on user acceptance (0-1)"""
        if self.final_item is None:
            return None

        accepted = []
        if self.user_accepted_category is not None:
            accepted.append(self.user_accepted_category)
        if self.user_accepted_title is not None:
            accepted.append(self.user_accepted_title)
        if self.user_accepted_price is not None:
            accepted.append(self.user_accepted_price)

        if not accepted:
            return None

        return sum(accepted) / len(accepted)


class QuotaUsageLog(models.Model):
    """
    Usage log for resource quotas (AI analysis, API calls, storage, etc.)

    Architecture:
    - Real-time limits: Redis (fast, atomic, auto-expiring)
    - Historical audit: PostgreSQL (this table)
    - See: parahub/services/quota.py for QuotaService
    """

    class ResourceType(models.TextChoices):
        AI_ANALYSIS = 'ai_analysis', 'AI Image Analysis'
        # Future: API_CALLS, STORAGE_MB, TOKENS, BANDWIDTH_GB, GEOCODING

    account = models.ForeignKey(
        'identity.Account',
        on_delete=models.CASCADE,
        related_name='quota_usage',
        help_text="Quota per account (shared across all profiles)"
    )
    resource_type = models.CharField(
        max_length=50,
        choices=ResourceType.choices,
        db_index=True
    )
    used_at = models.DateTimeField(auto_now_add=True, db_index=True)
    amount = models.IntegerField(
        default=1,
        help_text="Amount consumed (default 1 for count-based resources)"
    )
    metadata = models.JSONField(
        null=True,
        blank=True,
        help_text="Context: AI log_id, API endpoint, etc."
    )

    class Meta:
        verbose_name = "Quota Usage Log"
        verbose_name_plural = "Quota Usage Logs"
        indexes = [
            models.Index(fields=['account', 'resource_type', '-used_at']),
            models.Index(fields=['resource_type', '-used_at']),
        ]

    def __str__(self):
        return f"{self.account.username} - {self.resource_type} - {self.used_at.date()}"


class ZenithSettings(models.Model):
    """
    Zenith Protocol settings per profile.
    Each profile can have its own Zenith AI assistant configured.

    Architecture:
    - Knowledge base stored in Gitea repository (Markdown files)
    - AI powered by Google Gemini API
    - Access control via Partners system (contacts can ask your Zenith)
    """

    profile = models.OneToOneField(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='zenith_settings',
        help_text="Profile that owns this Zenith configuration"
    )

    # Enable/disable Zenith for this profile
    enabled = models.BooleanField(
        default=False,
        help_text="Enable Zenith AI assistant for this profile"
    )

    # Gitea repository configuration
    gitea_repo_name = models.CharField(
        max_length=100,
        blank=True,
        default='zenith-knowledge',
        help_text="Name of Gitea repository containing knowledge base (e.g., 'zenith-knowledge')"
    )

    # Google Gemini API key (per-user, optional - can use global)
    gemini_api_key = models.CharField(
        max_length=200,
        blank=True,
        help_text="Personal Google Gemini API key. If empty, uses global AISettings key."
    )

    # System prompt customization
    system_prompt = models.TextField(
        blank=True,
        default='',
        help_text="Custom system prompt for Zenith. If empty, uses default."
    )

    # Allow contacts to ask Zenith
    allow_contacts_access = models.BooleanField(
        default=True,
        help_text="Allow your contacts (partners) to ask your Zenith questions"
    )

    # Stats
    total_queries = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Zenith Settings"
        verbose_name_plural = "Zenith Settings"

    def __str__(self):
        status = "Enabled" if self.enabled else "Disabled"
        return f"Zenith for {self.profile.hna} - {status}"

    @classmethod
    def get_or_create_for_profile(cls, profile):
        """Get or create Zenith settings for a profile"""
        settings, created = cls.objects.get_or_create(profile=profile)
        return settings


class ZenithQueryLog(models.Model):
    """
    Log of Zenith queries for monitoring, debugging, and transparency.
    Owner can see all queries made to their Zenith.
    """

    # Who owns the Zenith being queried
    zenith_owner = models.ForeignKey(
        'identity.Profile',
        on_delete=models.CASCADE,
        related_name='zenith_queries_received',
        help_text="Profile whose Zenith was queried"
    )

    # Who asked the question (null if owner asking themselves)
    querier = models.ForeignKey(
        'identity.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='zenith_queries_made',
        help_text="Profile who made the query (null if owner)"
    )

    # Query details
    question = models.TextField(help_text="Question asked")
    answer = models.TextField(blank=True, help_text="Zenith's response")

    # Context used (which files were loaded)
    files_used = models.JSONField(
        default=list,
        help_text="List of .md files loaded as context"
    )

    # Performance & usage
    processing_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Time taken for Gemini API call"
    )
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    estimated_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True
    )

    # Error tracking
    error_message = models.TextField(blank=True)
    success = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Zenith Query Log"
        verbose_name_plural = "Zenith Query Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['zenith_owner', '-created_at']),
            models.Index(fields=['querier', '-created_at']),
        ]

    def __str__(self):
        querier_name = self.querier.hna if self.querier else "self"
        return f"Zenith query to {self.zenith_owner.hna} by {querier_name} - {self.created_at}"


class TranslationLog(models.Model):
    """One machine-translation provider call — the spend ledger for the MT path.

    Vision has `AIAnalysisLog` and Zenith has `ZenithQueryLog`; machine
    translation ran with no counter at all, so its cost was invisible. Rows stay
    cheap because the read path is cache-first: a call happens once per
    (object, language, field) and the result then lives in that row's
    `mt_cache` forever. A burst of rows for one object therefore means its cache
    is being wiped repeatedly (an edit loop) — worth being able to see.

    Failures are logged too (`success=False`). A provider outage degrades to the
    original text silently on the read path by design, and this is the only
    place that shows it happened.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    model_name = models.CharField(max_length=64, help_text="Provider model id the call was billed against")
    source_lang = models.CharField(max_length=10)
    target_lang = models.CharField(max_length=10)

    # What was translated. Blank when the caller did not name it — the service
    # never refuses to translate just because context is missing.
    object_type = models.CharField(max_length=32, blank=True, help_text="item, ad, civic_idea …")
    object_id = models.CharField(max_length=26, blank=True, db_index=True, help_text="ULID of the translated row")
    field_name = models.CharField(max_length=32, blank=True, help_text="title, description, body …")

    source_chars = models.IntegerField(default=0, help_text="Length of the source text")
    is_html = models.BooleanField(default=False, help_text="Went through the HTML-preserving prompt")

    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal('0'),
                                   help_text="Priced via services/ai_pricing; 0 when the model has no price entry")
    duration_ms = models.IntegerField(default=0)

    success = models.BooleanField(default=True)
    error_message = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Translation Log"
        verbose_name_plural = "Translation Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['target_lang', '-created_at']),
            models.Index(fields=['object_type', 'object_id']),
        ]

    def __str__(self):
        where = f"{self.object_type}.{self.field_name}" if self.object_type else "text"
        return f"MT {self.source_lang}->{self.target_lang} ({where}) - {self.created_at}"


class AIUsageLog(models.Model):
    """One paid model call from a path that has no ledger of its own.

    Vision has `AIAnalysisLog`, Zenith has `ZenithQueryLog`, machine translation
    has `TranslationLog`. Everything else — illustration and avatar generation,
    the ID-photo validator, the voice bot — spent money invisibly. This is the
    catch-all so that a new paid call site has somewhere to write on day one
    instead of shipping unmetered and being discovered later.

    Rows are written after the provider answers, success or not: a failed call
    that consumed tokens still costs money, and a burst of failures is the
    cheapest thing to notice here.

    Image generation is the reason the token columns are split three ways. An
    image comes back as output tokens billed at ~10x the text rate (Gemini 3 Pro
    Image: $120 vs $12 per 1M), so a single `output_tokens` column priced at one
    rate would understate an illustration by an order of magnitude. Providers
    that do not bill by token at all (speech) use `units`/`unit_kind` instead.
    """

    KIND_CMS_ILLUSTRATION = 'cms_illustration'
    KIND_AVATAR_STYLIZE = 'avatar_stylize'
    KIND_ID_PHOTO_VALIDATION = 'id_photo_validation'
    KIND_VOICE_STT = 'voice_stt'
    KIND_VOICE_THINK = 'voice_think'
    KIND_VOICE_TTS = 'voice_tts'
    KIND_VOICE_TRANSLATE = 'voice_translate'
    KIND_CHOICES = [
        (KIND_CMS_ILLUSTRATION, 'CMS illustration'),
        (KIND_AVATAR_STYLIZE, 'Avatar stylize'),
        (KIND_ID_PHOTO_VALIDATION, 'ID-photo validation'),
        (KIND_VOICE_STT, 'Voice — transcribe'),
        (KIND_VOICE_THINK, 'Voice — answer'),
        (KIND_VOICE_TTS, 'Voice — speak'),
        (KIND_VOICE_TRANSLATE, 'Voice — translate'),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True,
                            help_text="Which path spent the money")
    model_name = models.CharField(max_length=64, help_text="Provider model id the call was billed against")

    profile = models.ForeignKey(
        'identity.Profile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ai_usage_logs',
        help_text="Who triggered it; null for anonymous paths such as the voice bot"
    )

    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0, help_text="Text and thinking output — the text rate")
    image_tokens = models.IntegerField(default=0, help_text="Image-modality output — the image rate")

    units = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0'),
                                help_text="For providers not billed by token: characters, audio seconds")
    unit_kind = models.CharField(max_length=20, blank=True, help_text="What `units` counts")

    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal('0'),
                                   help_text="Priced via services/ai_pricing; 0 when the model has no price entry")
    duration_ms = models.IntegerField(default=0)

    success = models.BooleanField(default=True)
    error_message = models.CharField(max_length=300, blank=True)
    meta = models.JSONField(default=dict, blank=True,
                            help_text="Path-specific context: post id, source, session")

    class Meta:
        verbose_name = "AI Usage Log"
        verbose_name_plural = "AI Usage Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['kind', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} ({self.model_name}) - {self.created_at}"


class AISpend(AIAnalysisLog):
    """Proxy that exists only to hang the cross-provider spend dashboard off the
    admin — it stores nothing of its own.

    AI spend is split across ledgers written by unrelated subsystems
    (`AIAnalysisLog` for vision + categorization, `ZenithQueryLog`,
    `TranslationLog`, and `AIUsageLog` for everything else), so "what has AI cost
    me this month" could not be answered from any single changelist. The
    dashboard reads them all per day and adds them up, and names any path that is
    still unmetered so the total is never mistaken for everything.
    """
    class Meta:
        proxy = True
        verbose_name = "AI Spend"
        verbose_name_plural = "AI Spend"
