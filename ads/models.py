from django.db import models
from django.contrib.gis.db import models as gis_models

from django.utils import timezone
from core.models import ULIDModel
from identity.models import Profile
from finance.models import Payment
from market.models import Item
from geo.models import Establishment


# Reference data models (справочники)
class AdsInterest(ULIDModel):
    """Available interests for ad targeting."""
    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=128, unique=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'ads_interest'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class AdsSkill(ULIDModel):
    """Available skills for ad targeting."""
    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=128, unique=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'ads_skill'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class AdsChildrenAge(ULIDModel):
    """Children age ranges for family-targeted advertising."""
    name = models.CharField(max_length=128, unique=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'ads_children_age'
        ordering = ['order']

    def __str__(self):
        return self.name


class AdsProfileSkill(ULIDModel):
    """User's skill level (1-5: Beginner/Intermediate/Advanced/Expert/Master)."""
    profile = models.ForeignKey(
        'AdsProfile',
        on_delete=models.CASCADE,
        related_name='skill_ratings'
    )
    skill = models.ForeignKey(
        AdsSkill,
        on_delete=models.CASCADE
    )
    level = models.IntegerField(
        default=1,
        help_text="Skill level 1-5 (Beginner/Intermediate/Advanced/Expert/Master)"
    )

    class Meta:
        db_table = 'ads_profile_skill'
        unique_together = ('profile', 'skill')

    def __str__(self):
        return f"{self.profile} - {self.skill}: {self.level}/5"


class AdsProfile(ULIDModel):
    """User's advertising profile for targeting and earning statistics."""

    class Gender(models.TextChoices):
        ANY = 'any', 'Any'
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    profile = models.OneToOneField(
        Profile,
        on_delete=models.CASCADE,
        related_name="ads_profile"
    )

    # Targeting settings - Basic demographics
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        default=Gender.ANY
    )
    # Date of birth instead of age for more accurate targeting
    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of birth for age-based targeting"
    )
    # Keep age for backward compatibility and manual override
    age = models.IntegerField(null=True, blank=True)

    # Minimum payment threshold
    min_reward_sats = models.IntegerField(
        default=10,
        help_text="Minimum satoshis per ad view (user won't see ads below this)"
    )

    # Many-to-Many relationships with reference data
    interests = models.ManyToManyField(
        AdsInterest,
        blank=True,
        related_name='users',
        help_text="User's interests for targeted advertising"
    )
    children_ages = models.ManyToManyField(
        AdsChildrenAge,
        blank=True,
        related_name='users',
        help_text="Ages of user's children for family-targeted ads"
    )

    # Lightning wallet configuration (ln_address lives on Profile)
    ln_wallet_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Encrypted wallet credentials (admin keys for paying, invoice keys for receiving)"
    )

    # Earnings statistics
    total_views = models.IntegerField(default=0)
    total_earned_sats = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'ads_profile'
        indexes = [
            models.Index(fields=['gender', 'age']),
        ]

    def __str__(self):
        return f"AdsProfile for {self.profile}"


class AdsProfileLocation(ULIDModel):
    """User location for geo-targeted ads (max 3 per profile)."""
    profile = models.ForeignKey(AdsProfile, on_delete=models.CASCADE, related_name='locations')
    label = models.CharField(max_length=50)  # "Home", "Work", "Other"
    location = gis_models.PointField(srid=4326, geography=True)

    class Meta:
        db_table = 'ads_profile_location'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.label} for {self.profile}"


class AdCampaign(ULIDModel):
    """Advertising campaign created by users."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        COMPLETED = 'completed', 'Completed'

    class TargetGender(models.TextChoices):
        ANY = 'any', 'Any'
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    advertiser = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="ad_campaigns"
    )
    establishment = models.ForeignKey(
        'geo.Establishment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ad_campaigns',
        help_text="If set, campaign is posted on behalf of this establishment"
    )

    # Campaign info
    name = models.CharField(max_length=200)
    post_title = models.CharField(max_length=200)
    post_content = models.TextField()
    link = models.URLField(blank=True, max_length=500)

    # Banner image
    image = models.ImageField(upload_to='ads/%Y/%m/%d/', blank=True, null=True)

    # Linked content (promote an item or establishment)
    linked_item = models.ForeignKey(
        Item, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ad_campaigns',
        help_text="Linked marketplace item to promote"
    )
    linked_establishment = models.ForeignKey(
        Establishment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='promoted_campaigns',
        help_text="Linked establishment to promote"
    )

    # Pricing
    budget_sats = models.BigIntegerField()
    spent_sats = models.BigIntegerField(default=0)
    reward_sats = models.IntegerField(help_text="Satoshis paid per view")

    # Targeting
    target_gender = models.CharField(
        max_length=10,
        choices=TargetGender.choices,
        default=TargetGender.ANY
    )
    target_age_from = models.IntegerField(default=18)
    target_age_to = models.IntegerField(default=65)

    # Interest targeting
    target_interests = models.ManyToManyField(
        AdsInterest,
        blank=True,
        related_name='campaigns',
        help_text="Target users with these interests (empty = any interest)"
    )

    # Children age targeting
    target_children_ages = models.ManyToManyField(
        'AdsChildrenAge', blank=True, related_name='targeted_campaigns'
    )

    # Skills targeting
    target_skills = models.ManyToManyField(
        'AdsSkill', blank=True, related_name='targeted_campaigns'
    )
    target_min_skill_level = models.IntegerField(
        default=1,
        help_text='1-5, viewer must have at least one skill at this level or higher'
    )

    # Geo targeting
    target_location = gis_models.PointField(srid=4326, geography=True, null=True, blank=True)
    target_radius_km = models.FloatField(default=0, help_text="0 = no geo filter")

    # Self-targeting
    include_self = models.BooleanField(
        default=False,
        help_text="If True, always show to advertiser regardless of targeting (monitoring)"
    )
    exclude_self = models.BooleanField(
        default=False,
        help_text="If True, never show to advertiser even if matching targeting"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )

    # Statistics
    total_views = models.IntegerField(default=0)
    total_clicks = models.IntegerField(default=0)

    class Meta:
        db_table = 'ads_adcampaign'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['advertiser', 'status']),
        ]

    def __str__(self):
        return f"{self.name} by {self.advertiser}"

    @property
    def remaining_budget_sats(self):
        """Calculate remaining budget."""
        return max(0, self.budget_sats - self.spent_sats)

    @property
    def is_budget_exhausted(self):
        """Check if budget is exhausted."""
        return self.spent_sats >= self.budget_sats

    @property
    def ctr(self):
        """Calculate Click-Through Rate."""
        if self.total_views == 0:
            return 0.0
        return (self.total_clicks / self.total_views) * 100


class AdView(ULIDModel):
    """Track individual ad views and payments."""

    user = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="ad_views"
    )
    campaign = models.ForeignKey(
        AdCampaign,
        on_delete=models.CASCADE,
        related_name="views"
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="ad_view",
        null=True,
        blank=True
    )

    # Interaction tracking
    viewed_at = models.DateTimeField(default=timezone.now, db_index=True)
    clicked = models.BooleanField(default=False)
    clicked_at = models.DateTimeField(null=True, blank=True)

    # Payment tracking
    payment_sent = models.BooleanField(default=False)
    payment_amount_sats = models.IntegerField(default=0)
    payment_invoice = models.CharField(
        max_length=2000,
        blank=True,
        help_text="Lightning invoice used for payment"
    )
    payment_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ads_adview'
        unique_together = ('user', 'campaign')
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['campaign', '-viewed_at']),
            models.Index(fields=['user', '-viewed_at']),
            models.Index(fields=['payment_sent']),
        ]

    def __str__(self):
        return f"View of {self.campaign.name} by {self.user} at {self.viewed_at}"
