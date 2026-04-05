from django.apps import AppConfig


class GeoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'geo'

    def ready(self):
        from django.db.models.signals import post_save, post_delete
        from geo.models import Establishment, EstablishmentReview
        from geo.signals import update_establishment_rating_on_save, update_establishment_rating_on_delete
        post_save.connect(update_establishment_rating_on_save, sender=EstablishmentReview)
        post_delete.connect(update_establishment_rating_on_delete, sender=EstablishmentReview)

        def invalidate_map_caches(**kwargs):
            from django.core.cache import cache
            cache.delete_many(['geo:gov_map', 'geo:church_map'])

        post_save.connect(invalidate_map_caches, sender=Establishment)
        post_delete.connect(invalidate_map_caches, sender=Establishment)
