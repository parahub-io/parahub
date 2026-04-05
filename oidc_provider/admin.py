from django.contrib import admin
from .models import RSAKeyPair


@admin.register(RSAKeyPair)
class RSAKeyPairAdmin(admin.ModelAdmin):
    list_display = ['kid', 'is_active', 'created_at', 'expires_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['kid']
    readonly_fields = ['kid', 'public_key_pem', 'created_at', 'expires_at']
    exclude = ['private_key_pem']  # never expose private key in admin UI
