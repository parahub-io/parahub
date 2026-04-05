from django.db import models
from core.models import ULIDModel

class Category(ULIDModel):
    name = models.CharField(max_length=100, db_index=True, help_text="Default name (fallback)")
    slug = models.SlugField(max_length=100, unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    description = models.TextField(blank=True)

    # Multi-language support via JSON
    # Example: {"en": "Transport", "ru": "Транспорт", "es": "Transporte"}
    name_i18n = models.JSONField(default=dict, blank=True, help_text="Translated names by language code")
    description_i18n = models.JSONField(default=dict, blank=True, help_text="Translated descriptions by language code")

    # Metadata (existing fields from manual SQL migrations)
    icon = models.CharField(max_length=10, blank=True, help_text="Emoji icon for UI")
    image = models.CharField(max_length=255, blank=True, help_text="Image URL")
    is_active = models.BooleanField(default=True, help_text="Is category active")
    item_count = models.IntegerField(default=0, help_text="Number of items in category")
    order = models.IntegerField(default=0, help_text="Display order")

    # Sale/Rental constraints
    sale_only = models.BooleanField(
        default=False,
        help_text="Items in this category can only be sold, not rented (e.g., food, hygiene products)"
    )

    # Domain applicability: which subsystems use this category
    # Values: "market", "directory", "events"
    applicable_to = models.JSONField(
        default=list,
        blank=True,
        help_text='Subsystems: ["market"], ["directory"], ["market","directory"], ["events"]'
    )

    # Existing fields from core
    attributes = models.JSONField(default=dict, blank=True, help_text='Key-value store for intrinsic properties')
    relations = models.JSONField(default=list, blank=True, help_text='List of relationships to other objects')

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def get_name(self, language='en'):
        """Get translated name or fallback to default"""
        return self.name_i18n.get(language, self.name)

    def get_description(self, language='en'):
        """Get translated description or fallback to default"""
        return self.description_i18n.get(language, self.description)

    def get_path(self):
        """Get full path from root to this category as list of dicts"""
        path = []
        current = self
        while current:
            path.insert(0, {
                'id': current.id,
                'name': current.name,
                'slug': current.slug
            })
            current = current.parent
        return path

    @property
    def is_leaf(self):
        """Check if category is a leaf node (has no children)"""
        return not self.children.exists()

class Tag(ULIDModel):
    name = models.CharField(max_length=100, unique=True, db_index=True)

    def __str__(self):
        return self.name
