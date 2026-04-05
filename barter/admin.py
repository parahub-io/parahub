from django.contrib import admin
from barter.models import Exchange, ExchangeSwap, ExchangeApproval


class ExchangeSwapInline(admin.TabularInline):
    model = ExchangeSwap
    extra = 0
    readonly_fields = ('id', 'from_user', 'to_user', 'offered_item', 'wanted_item', 'order')
    can_delete = False


class ExchangeApprovalInline(admin.TabularInline):
    model = ExchangeApproval
    extra = 0
    readonly_fields = ('id', 'user', 'approved', 'created_at')
    can_delete = False


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'participant_count', 'category', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user_chain')
    readonly_fields = ('id', 'user_chain', 'created_at', 'updated_at', 'version')
    inlines = [ExchangeSwapInline, ExchangeApprovalInline]

    def participant_count(self, obj):
        return len(obj.participants)
    participant_count.short_description = 'Participants'


@admin.register(ExchangeSwap)
class ExchangeSwapAdmin(admin.ModelAdmin):
    list_display = ('id', 'exchange', 'order', 'from_user', 'to_user')
    list_filter = ('created_at',)
    search_fields = ('id', 'exchange__id', 'from_user__hna', 'to_user__hna')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(ExchangeApproval)
class ExchangeApprovalAdmin(admin.ModelAdmin):
    list_display = ('id', 'exchange', 'user', 'approved', 'created_at')
    list_filter = ('approved', 'created_at')
    search_fields = ('id', 'exchange__id', 'user__hna')
    readonly_fields = ('id', 'created_at', 'updated_at')
