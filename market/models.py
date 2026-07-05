from django.db import models
from django.contrib.gis.db import models as gis_models
from django.db.models import F
from core.models import ULIDModel
from identity.models import Profile
from taxonomy.models import Category, Tag

class Item(ULIDModel):

    class ItemType(models.TextChoices):
        CREDIT = 'CREDIT', 'Offer'
        DEBIT = 'DEBIT', 'Request'

    class Visibility(models.TextChoices):
        # Audience scope. Default PUBLIC keeps the civic-router discoverable;
        # REGISTERED is opt-in. A future CIRCLE (WoT graph) tier is intentionally
        # NOT defined yet — it needs a precise circle definition + graph caching,
        # and an undefined-but-settable value would leak (no enforcement path).
        PUBLIC = 'PUBLIC', 'Public — anyone, incl. anonymous & search engines'
        REGISTERED = 'REGISTERED', 'Registered — signed-in parahub users only'

    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=150, blank=True, default='', db_index=True,
                            help_text="URL-friendly identifier, auto-generated from title")
    description = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=ItemType.choices, db_index=True)
    spec_data = models.JSONField(default=dict, blank=True)
    location = gis_models.PointField(srid=4326, geography=True, null=True, blank=True)

    # Modern flexible pricing system
    pricing_options = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Array of pricing options. Each option: "
            "{type: 'sale'|'rent'|'free', amount: number, currency: 'EUR'|'USD'|..., "
            "unit?: 'kg'|'hour'|'day'|'pcs'|..., note?: string}. "
            "Examples: [{type: 'sale', amount: 2, currency: 'EUR', unit: 'kg'}, "
            "{type: 'rent', amount: 800, currency: 'EUR', unit: 'month'}]"
        )
    )

    accepted_payment_methods = models.JSONField(default=list, blank=True, help_text="Array of accepted payment method codes")
    is_active = models.BooleanField(default=True, db_index=True)

    visibility = models.CharField(
        max_length=12, choices=Visibility.choices, default=Visibility.PUBLIC, db_index=True,
        help_text=(
            "Audience scope. PUBLIC = discoverable by anyone incl. anonymous "
            "visitors and search engines (default). REGISTERED = hidden from "
            "anonymous + SEO, visible only to signed-in parahub users. "
            "Orthogonal to is_active (which is the draft/paused switch)."
        ),
    )

    language = models.CharField(
        max_length=5, blank=True, default='', db_index=True,
        help_text="Content language (ISO 639-1: en/ru/pt/es/fr/de). Empty = unspecified (shown to all)."
    )
    is_international = models.BooleanField(
        default=False, db_index=True,
        help_text="Visible to all users regardless of language filter (e.g. remote services, souvenirs)"
    )
    country_code = models.CharField(
        max_length=2, blank=True, default='', db_index=True,
        help_text="ISO 3166-1 alpha-2 country code from item coordinates. Empty = no location/digital."
    )

    self_made = models.BooleanField(
        default=False, db_index=True,
        help_text=(
            "Seller is the producer — made / grew / prepared it themselves — not a "
            "reseller. Drives the 'made by hand' badge and a ranking nudge (swadeshi / "
            "bread-labour: prefer own-and-near). Bought parts/ingredients don't "
            "disqualify; reselling finished goods does. Offers (CREDIT) only."
        )
    )

    establishment = models.ForeignKey(
        'geo.Establishment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='posted_items',
        help_text="If set, item is posted on behalf of this establishment"
    )

    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    tags = models.ManyToManyField(Tag, blank=True, related_name="items")
    
    # Add version field for optimistic locking
    version = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'type', '-created_at']),
            models.Index(fields=['owner', 'is_active', '-created_at']),
            models.Index(fields=['is_active', 'language', 'country_code']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['slug'], name='unique_item_slug',
                condition=~models.Q(slug=''),
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()}: {self.title}"

    def save(self, *args, **kwargs):
        # Auto-generate slug on creation
        if self._state.adding and not self.slug:
            self.slug = self._generate_slug()
        # Increment version on updates
        if not self._state.adding:
            self.version = F('version') + 1
        super().save(*args, **kwargs)

    def _generate_slug(self):
        from django.utils.text import slugify
        base = slugify(self.title)[:80] or self.id[:8].lower()
        candidate = base
        counter = 2
        while Item.objects.filter(slug=candidate).exclude(id=self.id).exists():
            suffix = str(counter)
            candidate = f"{base[:80 - len(suffix) - 1]}-{suffix}"
            counter += 1
        return candidate





