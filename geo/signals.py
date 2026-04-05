from django.db.models.signals import post_save, post_delete
from django.db.models import Avg, Count
from django.dispatch import receiver


def _update_establishment_rating(establishment):
    from geo.models import EstablishmentReview, Establishment
    result = EstablishmentReview.objects.filter(establishment=establishment).aggregate(
        avg=Avg('rating'), count=Count('id')
    )
    Establishment.objects.filter(id=establishment.id).update(
        rating_avg=result['avg'] or 0,
        rating_count=result['count'] or 0
    )


def update_establishment_rating_on_save(sender, instance, **kwargs):
    _update_establishment_rating(instance.establishment)


def update_establishment_rating_on_delete(sender, instance, **kwargs):
    _update_establishment_rating(instance.establishment)
