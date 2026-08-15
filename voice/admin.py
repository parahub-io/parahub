from django.contrib import admin

from voice.models import VoiceClone, VoiceConsent, VoiceNote


@admin.register(VoiceConsent)
class VoiceConsentAdmin(admin.ModelAdmin):
    list_display = ('profile', 'granted_at', 'revoked_at', 'consent_text_version')
    list_filter = ('consent_text_version',)
    search_fields = ('profile__local_name', 'profile__display_name')
    readonly_fields = ('granted_at',)
    # Consent rows are the evidence that processing was lawful — the admin may
    # read them, never rewrite them.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VoiceClone)
class VoiceCloneAdmin(admin.ModelAdmin):
    list_display = ('profile', 'voice_id', 'stage', 'sample_seconds', 'status', 'last_used_at')
    list_filter = ('status', 'stage', 'provider')
    search_fields = ('profile__local_name', 'voice_id')


@admin.register(VoiceNote)
class VoiceNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'recipient', 'source_lang', 'target_lang',
                    'audio_seconds', 'created_at', 'played_at')
    list_filter = ('source_lang', 'target_lang', 'translation_model')
    search_fields = ('sender__local_name', 'recipient__local_name')
    readonly_fields = ('created_at', 'updated_at')
