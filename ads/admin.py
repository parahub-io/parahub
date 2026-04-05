from django.contrib import admin
from .models import AdsProfile, AdCampaign, AdView


@admin.register(AdsProfile)
class AdsProfileAdmin(admin.ModelAdmin):
    list_display = ['profile', 'gender', 'age', 'total_views', 'total_earned_sats', 'created_at']
    list_filter = ['gender', 'created_at']
    search_fields = ['profile__local_name', 'profile__hna']
    readonly_fields = ['id', 'total_views', 'total_earned_sats', 'created_at', 'updated_at']

    fieldsets = (
        ('Profile', {
            'fields': ('id', 'profile')
        }),
        ('Targeting', {
            'fields': ('gender', 'age', 'interests')
        }),
        ('Lightning Wallet', {
            'fields': ('ln_wallet_config',)
        }),
        ('Statistics', {
            'fields': ('total_views', 'total_earned_sats')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'advertiser', 'status', 'reward_sats', 'budget_sats',
        'spent_sats', 'total_views', 'total_clicks', 'ctr_display', 'created_at'
    ]
    list_filter = ['status', 'target_gender', 'created_at']
    search_fields = ['name', 'title', 'post_title', 'advertiser__local_name', 'advertiser__hna']
    readonly_fields = ['id', 'total_views', 'total_clicks', 'spent_sats', 'ctr_display', 'remaining_budget_display', 'created_at', 'updated_at']

    fieldsets = (
        ('Campaign Info', {
            'fields': ('id', 'advertiser', 'name', 'status')
        }),
        ('Content', {
            'fields': ('post_title', 'post_content', 'link')
        }),
        ('Pricing', {
            'fields': ('reward_sats', 'budget_sats', 'spent_sats', 'remaining_budget_display')
        }),
        ('Targeting', {
            'fields': ('target_gender', 'target_age_from', 'target_age_to')
        }),
        ('Statistics', {
            'fields': ('total_views', 'total_clicks', 'ctr_display')
        }),
        ('Legacy Fields', {
            'fields': ('title', 'price_per_view_sats', 'is_active', 'content_data', 'targeting_criteria'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def ctr_display(self, obj):
        """Display CTR as percentage"""
        return f"{obj.ctr:.2f}%"
    ctr_display.short_description = 'CTR'

    def remaining_budget_display(self, obj):
        """Display remaining budget"""
        return f"{obj.remaining_budget_sats} sats"
    remaining_budget_display.short_description = 'Remaining Budget'


@admin.register(AdView)
class AdViewAdmin(admin.ModelAdmin):
    list_display = [
        'campaign_name', 'user', 'viewed_at', 'clicked',
        'payment_sent', 'payment_amount_sats', 'created_at'
    ]
    list_filter = ['clicked', 'payment_sent', 'viewed_at', 'created_at']
    search_fields = ['user__local_name', 'user__hna', 'campaign__name', 'campaign__title']
    readonly_fields = ['id', 'viewed_at', 'clicked_at', 'payment_sent_at', 'created_at', 'updated_at']

    fieldsets = (
        ('View Info', {
            'fields': ('id', 'campaign', 'user', 'viewed_at')
        }),
        ('Interaction', {
            'fields': ('clicked', 'clicked_at')
        }),
        ('Payment', {
            'fields': ('payment', 'payment_sent', 'payment_amount_sats', 'payment_invoice', 'payment_sent_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def campaign_name(self, obj):
        """Display campaign name"""
        return obj.campaign.name or obj.campaign.title
    campaign_name.short_description = 'Campaign'
    campaign_name.admin_order_field = 'campaign__name'
