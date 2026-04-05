from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Account, Profile, Verification, SocialRecovery, Partner, Contract, PGPKeyHistory, PsychProfile, ProfileNote


class TestUserFilter(admin.SimpleListFilter):
    """Filter for test users (members of test_users group)."""
    title = 'test user'
    parameter_name = 'is_test_user'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Test Users'),
            ('no', 'Regular Users'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(groups__name='test_users')
        if self.value() == 'no':
            return queryset.exclude(groups__name='test_users')
        return queryset


class AccountAdmin(UserAdmin):
    """Admin for custom Account model."""
    list_display = ['username', 'email', 'instance', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_active', 'instance', TestUserFilter]
    fieldsets = UserAdmin.fieldsets + (
        ('ParaHub', {'fields': ('instance', 'preferences')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('ParaHub', {'fields': ('instance',)}),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['local_name', 'display_name', 'instance', 'reputation_score', 'is_verified_wot']
    list_filter = ['is_verified_wot', 'instance']
    search_fields = ['local_name', 'display_name']
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ['verifier', 'verified_profile', 'created_at']
    list_filter = ['created_at']
    search_fields = ['verifier__local_name', 'verified_profile__local_name']


@admin.register(SocialRecovery)
class SocialRecoveryAdmin(admin.ModelAdmin):
    list_display = ['account', 'trustee', 'created_at']
    list_filter = ['created_at']
    search_fields = ['account__username', 'trustee__local_name']
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ['profile', 'partner_profile', 'added_at']
    list_filter = ['added_at']
    search_fields = ['profile__local_name', 'partner_profile__local_name']
    readonly_fields = ['added_at']


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'creator', 'partner', 'status', 'creator_signed_at', 'partner_signed_at']
    list_filter = ['status', 'creator_signed_at']
    search_fields = ['title', 'creator__local_name', 'partner__local_name', 'file_sha256']
    readonly_fields = ['id', 'file_sha256', 'creator_signature', 'partner_signature',
                       'creator_signed_at', 'partner_signed_at', 'creator_completed_at',
                       'partner_completed_at', 'arbitration_initiated_at']


@admin.register(PGPKeyHistory)
class PGPKeyHistoryAdmin(admin.ModelAdmin):
    list_display = ['profile', 'fingerprint', 'action', 'action_timestamp', 'valid_from', 'valid_until']
    list_filter = ['action', 'action_timestamp']
    search_fields = ['profile__local_name', 'fingerprint']
    readonly_fields = ['id', 'profile', 'fingerprint', 'public_key', 'action', 'action_timestamp',
                       'valid_from', 'valid_until']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PsychProfile)
class PsychProfileAdmin(admin.ModelAdmin):
    list_display = ['profile', 'psych_hash_4_display', 'form3_completed_at', 'psych_hash_4_updated_at']
    search_fields = ['profile__local_name']
    readonly_fields = ['id', 'form3_completed_at', 'psych_hash_4_updated_at']

    @admin.display(description='Psych Hash (4)')
    def psych_hash_4_display(self, obj):
        return ', '.join(obj.psych_hash_4) if obj.psych_hash_4 else '—'


@admin.register(ProfileNote)
class ProfileNoteAdmin(admin.ModelAdmin):
    list_display = ['owner', 'about', 'created_at']
    list_filter = ['created_at']
    search_fields = ['owner__local_name', 'about__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at']


# Register the custom Account model
admin.site.register(Account, AccountAdmin)