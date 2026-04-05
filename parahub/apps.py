"""
Parahub app configuration
"""

from django.apps import AppConfig


class ParahubConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parahub'
    verbose_name = 'Parahub Core'

    def ready(self):
        from parahub.signals.object_publish import connect_signals
        connect_signals()
