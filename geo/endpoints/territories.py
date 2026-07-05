"""
Territory reference API (civic polls): administrative hierarchy search for residency pickers.
"""
from typing import List, Optional

from ninja import Router
from pydantic import BaseModel

from parahub.ratelimit import ratelimit
from geo.models import Territory

router = Router()


class TerritorySchema(BaseModel):
    id: str
    object_type: str = "territory"
    level: str
    country: str
    code: str
    name: str
    parent_id: Optional[str] = None


@router.get("/territories/", response=List[TerritorySchema], auth=None)
@ratelimit(group='geo:territories', key='ip', rate='60/m')
def list_territories(request, country: Optional[str] = None, level: Optional[str] = None,
                     parent_id: Optional[str] = None, q: Optional[str] = None,
                     page: int = 1, page_size: int = 50):
    """Public reference lookup for cascading residency pickers (country → municipality → parish)."""
    page_size = min(max(page_size, 1), 200)
    qs = Territory.objects.filter(is_active=True)
    if country:
        qs = qs.filter(country=country.upper())
    if level:
        qs = qs.filter(level=level)
    if parent_id:
        qs = qs.filter(parent_id=parent_id)
    if q:
        qs = qs.filter(name__icontains=q)
    qs = qs.order_by('name')[(page - 1) * page_size: page * page_size]
    return [
        TerritorySchema(id=t.id, level=t.level, country=t.country, code=t.code,
                        name=t.name, parent_id=t.parent_id)
        for t in qs
    ]
