from django.apps import AppConfig


class BarterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'barter'
    verbose_name = 'Barter Exchange System'

    def ready(self):
        """Import signals when app is ready"""
        import barter.signals  # noqa
