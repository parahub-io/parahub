from django.apps import AppConfig


class AuditLogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit_log'

    def ready(self):
        """Import signal handlers when app is ready"""
        import audit_log.signals  # noqa
