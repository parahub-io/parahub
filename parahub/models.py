"""
Parahub core models
"""

from django.db import models


class AISettings(models.Model):
    """
    AI Vision API settings (singleton model - only one instance)
    Configurable via Django admin
    """

    class Provider(models.TextChoices):
        HAIKU = 'haiku', 'Claude Haiku 4.5 ($1/$5 per 1M)'
        GPT5_MINI = 'gpt-5-mini', 'GPT-5 mini ($0.50/$5 per 1M)'
        GPT5_NANO = 'gpt-5-nano', 'GPT-5 nano ($0.15/$1.50 per 1M)'
        GEMINI_FLASH = 'gemini-flash', 'Gemini 2.5 Flash ($0.30/$2.50 per 1M)'
        GEMINI_FLASH_LITE = 'gemini-flash-lite', 'Gemini 2.5 Flash-Lite ($0.10/$0.40 per 1M)'

    class CategorizationProvider(models.TextChoices):
        HAIKU = 'haiku', 'Claude Haiku 4.5 ($1/$5 per 1M)'
        GPT5_NANO = 'gpt-5-nano', 'GPT-5 nano ($0.15/$1.50 per 1M)'
        GPT5_MINI = 'gpt-5-mini', 'GPT-5 mini ($0.50/$5 per 1M)'
        GEMINI_FLASH = 'gemini-flash', 'Gemini 2.5 Flash ($0.30/$2.50 per 1M)'
        GEMINI_FLASH_LITE = 'gemini-flash-lite', 'Gemini 2.5 Flash-Lite ($0.10/$0.40 per 1M)'
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
        """Get the singleton instance"""
        instance, created = cls.objects.get_or_create(pk=1)
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
        return f"{self.account.user.username} - {self.resource_type} - {self.used_at.date()}"


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
