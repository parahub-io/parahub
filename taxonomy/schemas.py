"""
Pydantic schemas for taxonomy API endpoints
"""

from typing import List, Optional, Dict
from ninja import Schema


class BreadcrumbSchema(Schema):
    """Schema for breadcrumb in category path"""
    id: str
    name: str
    slug: str
    icon: str = ""


class CategorySchema(Schema):
    """Schema for Category model"""
    id: str  # CRI
    name: str
    slug: str
    description: str = ""
    icon: str = ""
    parent_id: Optional[str] = None  # CRI of parent

    # Sale/Rental constraints
    sale_only: bool = False

    # i18n support
    name_i18n: Dict[str, str] = {}
    description_i18n: Dict[str, str] = {}

    # Computed fields
    has_children: bool = False
    breadcrumbs: List['BreadcrumbSchema'] = []  # Full path from root to this category


class CategoryTreeSchema(Schema):
    """Schema for hierarchical category tree"""
    id: str
    name: str
    slug: str
    icon: str = ""
    applicable_to: List[str] = []
    children: List['CategoryTreeSchema'] = []


# Update forward references
CategorySchema.update_forward_refs()
CategoryTreeSchema.update_forward_refs()


class CategoryListResponse(Schema):
    """Response for category list endpoints"""
    count: int
    results: List[CategorySchema]


class TranslatedCategorySchema(Schema):
    """Schema for category with language-specific translations"""
    id: str
    name: str  # Translated name
    slug: str
    description: str  # Translated description
    icon: str = ""
    parent_id: Optional[str] = None
    sale_only: bool = False
    has_children: bool = False
