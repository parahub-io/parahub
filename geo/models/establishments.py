from django.contrib.gis.db import models
from django.core.validators import RegexValidator
from core.models import ULIDModel
from identity.models import Profile
from market.models import Item
from taxonomy.models import Category


class WorldObject(ULIDModel):
    """Any real-world entity that needs a ULID for interactions.

    Absorbs the former Building model. Represents buildings, parks, POIs, or any
    OSM/external entity. Lifecycle: get_or_create(xeno_source, xeno_id) on first interaction.
    """

    # External identity (how we found it)
    xeno_source = models.CharField(max_length=20, blank=True, db_index=True,
                                    help_text="Source system: osm, traccar, ha, external")
    xeno_id = models.CharField(max_length=100, blank=True, db_index=True,
                                help_text="External ID: way/1168594818, node/123456")

    # Geo
    location = models.PointField(srid=4326, geography=True, null=True, blank=True)

    # Geometry (absorbed from Building)
    geometry = models.PolygonField(srid=4326, geography=True, null=True, blank=True,
                                   help_text="Footprint polygon (buildings, parks, etc.)")

    # Address (absorbed from Building)
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    city = models.CharField(max_length=255, blank=True)
    street = models.CharField(max_length=255, blank=True)
    house_number = models.CharField(max_length=20, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    full_address = models.CharField(max_length=500, blank=True, db_index=True)

    # Building metadata (absorbed from Building)
    building_type = models.CharField(max_length=50, blank=True,
                                      help_text="OSM building type: residential, commercial, etc.")
    levels = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Number of floors")

    # Stats (denormalized)
    establishments_count = models.PositiveIntegerField(default=0)

    # Ownership
    owner = models.ForeignKey('identity.Profile', null=True, blank=True,
                              on_delete=models.SET_NULL, related_name='owned_objects')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['xeno_source', 'xeno_id'],
                condition=~models.Q(xeno_id=''),
                name='unique_xeno_identity'
            )
        ]
        indexes = [
            models.Index(fields=['xeno_source', 'xeno_id']),
            models.Index(fields=['city', 'street']),
            models.Index(fields=['country', 'city']),
        ]

    def __str__(self):
        if self.xeno_source and self.xeno_id:
            return f"WorldObject({self.xeno_source}:{self.xeno_id})"
        return f"WorldObject({self.id})"

class Establishment(ULIDModel):
    """Unified business entity: physical places, online businesses, associations, networks."""

    class OrganizationType(models.TextChoices):
        ASSOCIATION = 'ASSOCIATION', 'Association'
        COOPERATIVE = 'COOPERATIVE', 'Cooperative'
        COMPANY = 'COMPANY', 'Company'
        NGO = 'NGO', 'NGO'
        COMMUNITY = 'COMMUNITY', 'Community'
        CONDOMINIUM = 'CONDOMINIUM', 'Condominium'
        GOVERNMENT = 'GOVERNMENT', 'Government'

    class MemberVisibility(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public'
        MEMBERS_ONLY = 'MEMBERS_ONLY', 'Members only'
        PRIVATE = 'PRIVATE', 'Private'

    # Ownership & linking
    owner = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="establishments",
                              help_text="Profile that manages this establishment")
    world_object = models.ForeignKey(WorldObject, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='establishments')

    # Network/franchise structure
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='branches', help_text="Parent establishment for franchises/networks")

    # Basic info
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=100, blank=True, db_index=True,
                            help_text="URL-friendly name (e.g., parahub-associacao)")
    description = models.TextField(blank=True)
    is_online = models.BooleanField(default=False, help_text="Online-only business (no physical location)")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="establishments", help_text="Primary business category")

    # Organization/association fields
    organization_type = models.CharField(max_length=20, choices=OrganizationType.choices, blank=True,
                                         help_text="Type if this is an organization/association")
    legal_entity_id = models.CharField(max_length=50, blank=True, help_text="NIF/NIPC/Tax ID")
    member_visibility = models.CharField(max_length=20, choices=MemberVisibility.choices,
                                         default=MemberVisibility.PUBLIC,
                                         help_text="Who can see members list")
    requires_terms_acceptance = models.BooleanField(default=False,
                                                     help_text="Members must accept terms before joining")
    terms_url = models.CharField(max_length=255, blank=True, help_text="URL to terms/estatutos page")
    terms_content = models.TextField(blank=True, help_text="Full text of terms/estatutos (markdown)")

    # Treasury (participatory budget)
    treasury_enabled = models.BooleanField(default=False, help_text="Enable Treasury for this establishment")
    treasury_eligible_levels = models.JSONField(default=list, blank=True,
                                                 help_text="Membership levels eligible to vote, e.g. ['efetivo','fundador']")

    # Communication
    matrix_room_id = models.CharField(max_length=255, blank=True, help_text="Matrix room ID for org chat")

    # Payments
    ln_address = models.CharField(max_length=255, blank=True, help_text="Lightning address for payments")
    spark_address = models.CharField(max_length=512, blank=True, help_text="Spark address for P2P payments")

    # Membership (M2M through EstablishmentMembership)
    members = models.ManyToManyField(Profile, through='EstablishmentMembership', related_name="member_of_establishments",
                                     blank=True)

    # Location (if not in building, e.g. outdoor kiosk)
    location = models.PointField(srid=4326, geography=True, null=True, blank=True,
                                 help_text="Precise location if different from building center")
    floor = models.CharField(max_length=10, blank=True, help_text="Floor number or range (e.g., '2', '2-3')")
    office_number = models.CharField(max_length=50, blank=True, help_text="Office/suite number")

    # Contact information
    phone = models.CharField(max_length=50, blank=True, validators=[
        RegexValidator(r'^\+?[\d\s\-\(\)]+$', 'Enter valid phone number')
    ])
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Social media (JSON for extensibility)
    social_links = models.JSONField(default=dict, blank=True, help_text="Social media handles")

    # Opening hours (OSM format)
    opening_hours = models.JSONField(default=dict, blank=True, help_text="Opening hours by day")

    # Media
    logo_url = models.URLField(blank=True, help_text="Organization logo")
    photos = models.JSONField(default=list, blank=True, help_text="Array of photo URLs")

    # Items showcase (products/services)
    items = models.ManyToManyField(Item, blank=True, related_name="establishments",
                                   help_text="Items sold/offered at this establishment")

    # Stats & moderation
    views_count = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    rating_count = models.PositiveIntegerField(default=0)
    is_verified = models.BooleanField(default=False, help_text="Verified by moderators")
    is_active = models.BooleanField(default=True, db_index=True)

    # P-Hub (logistics point)
    is_hub = models.BooleanField(default=False, db_index=True, help_text="Enables P-Hub mode (drop-off/pick-up point)")
    hub_capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Max parcels (null = unlimited)")
    hub_max_days = models.PositiveSmallIntegerField(default=14, help_text="Max storage days before expiry")
    hub_storage_fee_daily = models.PositiveIntegerField(default=0, help_text="Storage fee in sats/day (0 = free)")
    hub_accepted_sizes = models.JSONField(default=list, blank=True, help_text='Accepted sizes: ["S","M","L","XL"]')
    hub_instructions = models.TextField(blank=True, help_text="Pickup/dropoff instructions (e.g. 'enter from backyard')")

    # Extensible attributes (EAV pattern for future)
    attributes = models.JSONField(default=dict, blank=True,
                                  help_text="Custom attributes (parking, wifi, accessibility, etc)")

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['world_object', 'is_active']),
            models.Index(fields=['organization_type', 'is_active']),
            models.Index(fields=['owner', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['slug'], name='unique_establishment_slug',
                condition=~models.Q(slug=''),
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.world_object.full_address if self.world_object else self.slug or 'no address'})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    def _generate_slug(self):
        from django.utils.text import slugify
        base = slugify(self.name)[:80] or self.id[:8].lower()
        candidate = base
        counter = 2
        while Establishment.objects.filter(slug=candidate).exclude(id=self.id).exists():
            suffix = str(counter)
            candidate = f"{base[:80 - len(suffix) - 1]}-{suffix}"
            counter += 1
        return candidate

class EstablishmentMembership(models.Model):
    """Membership in an establishment/organization."""

    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        MEMBER = 'MEMBER', 'Member'
        EMPLOYEE = 'EMPLOYEE', 'Employee'
        CONTRACTOR = 'CONTRACTOR', 'Contractor'

    class MembershipLevel(models.TextChoices):
        APOIANTE = 'apoiante', 'Associado Apoiante'
        EFETIVO = 'efetivo', 'Associado Efetivo'
        FUNDADOR = 'fundador', 'Associado Fundador'

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='establishment_memberships')
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    membership_level = models.CharField(
        max_length=20, choices=MembershipLevel.choices, blank=True, null=True,
        help_text="Membership level for associations (apoiante, efetivo, fundador)"
    )
    terms_accepted_at = models.DateTimeField(null=True, blank=True,
                                              help_text="When member accepted terms")
    employment_start_date = models.DateField(null=True, blank=True)
    employment_end_date = models.DateField(null=True, blank=True)

    position_title = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Custom position title (e.g. Vice-Presidente, Secretário) — shown instead of generic role label"
    )
    is_treasurer = models.BooleanField(
        default=False,
        help_text="Designated treasurer — wallet receives establishment payments"
    )
    is_auditor = models.BooleanField(
        default=False,
        help_text="Designated auditor (Fiscal Único) — read-only access to all financial data"
    )

    class Meta:
        unique_together = ('profile', 'establishment')
        indexes = [
            models.Index(fields=['establishment', 'role']),
            models.Index(fields=['profile', 'created_at']),
        ]

    def __str__(self):
        return f"{self.profile.hna} → {self.establishment.name} ({self.role})"

class EstablishmentReview(ULIDModel):
    """User review and star rating for an establishment."""
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='reviews')
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='establishment_reviews')
    rating = models.SmallIntegerField()  # 1-5
    text = models.TextField(blank=True)
    wot_count_snapshot = models.PositiveSmallIntegerField(default=0)  # verifications at review time
    owner_reply = models.TextField(blank=True)

    class Meta:
        unique_together = ('establishment', 'author')
        indexes = [
            models.Index(fields=['establishment', '-created_at']),
        ]

    def __str__(self):
        return f"{self.author.hna} → {self.establishment.name} ({self.rating}★)"
