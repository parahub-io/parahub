"""
Parahub Django Admin
"""

from django.contrib import admin
from django.utils.html import format_html
from parahub.models import (AISettings, AIAnalysisLog, QuotaUsageLog, ZenithSettings,
                            ZenithQueryLog, TranslationLog, AIUsageLog, AISpend)


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ('provider', 'categorization_provider', 'enabled', 'total_requests', 'updated_at')
    readonly_fields = ('total_requests', 'updated_at')

    fieldsets = (
        ('Status', {
            'fields': ('enabled',)
        }),
        ('Two-Step AI Configuration', {
            'fields': ('provider', 'categorization_provider', 'use_single_request'),
            'description': 'Step 1: Vision provider analyzes image → title/description. Step 2: Categorization provider selects category from text (cheaper, sees ALL categories). Enable "Use single request" to combine both steps (faster, works for Claude/OpenAI/Gemini when same provider).'
        }),
        ('API Keys', {
            'fields': ('claude_api_key', 'openai_api_key', 'google_api_key'),
            'description': 'Enter API key for your selected provider. One key can be used for both vision and categorization if provider supports it.'
        }),
        ('Statistics', {
            'fields': ('total_requests', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """Label each provider tier with the model id and rate it really bills.

        The choices themselves carry no numbers (see AISettings.Provider) — they
        are read from the price table here, so repointing a tier or a price
        change updates the dropdown instead of leaving it advertising an old one.
        """
        if db_field.name in ('provider', 'categorization_provider'):
            from parahub.services.ai_pricing import tier_label
            kwargs['choices'] = [(value, tier_label(label, value))
                                 for value, label in db_field.choices]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def has_add_permission(self, request):
        # Singleton - only one instance allowed
        return not AISettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Cannot delete singleton
        return False


@admin.register(AIAnalysisLog)
class AIAnalysisLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'profile', 'vision_provider', 'categorization_provider',
                   'suggested_category', 'vision_cost_display', 'categorization_cost_display',
                   'total_cost_display', 'vision_time_display', 'categorization_time_display',
                   'total_time_display', 'final_item')
    list_filter = ('vision_provider', 'categorization_provider', 'created_at', 'suggested_category', 'language')
    search_fields = ('id', 'profile__hna', 'suggested_title', 'error_message')
    list_display_links = ('id', 'created_at')
    readonly_fields = ('created_at', 'profile', 'language', 'image_filename', 'image_size_original',
                      'image_size_compressed', 'vision_provider', 'categorization_provider',
                      'suggested_category', 'suggested_category_confidence', 'suggested_title',
                      'suggested_description', 'suggested_price', 'overall_confidence',
                      'processing_time_ms', 'vision_processing_time_ms', 'categorization_processing_time_ms',
                      'vision_input_tokens', 'vision_output_tokens', 'vision_cost_usd',
                      'categorization_input_tokens', 'categorization_output_tokens', 'categorization_cost_usd',
                      'input_tokens', 'output_tokens', 'estimated_cost_usd',
                      'error_message', 'final_item',
                      'user_accepted_category', 'user_accepted_title', 'user_accepted_price',
                      'vision_request_prompt', 'vision_response_raw',
                      'categorization_request_prompt', 'categorization_response_raw')

    date_hierarchy = 'created_at'

    fieldsets = (
        ('Request Info', {
            'fields': ('created_at', 'profile', 'language', 'processing_time_ms',
                      'vision_processing_time_ms', 'categorization_processing_time_ms')
        }),
        ('Providers (Two-Step)', {
            'fields': ('vision_provider', 'categorization_provider')
        }),
        ('Image Info', {
            'fields': ('image_filename', 'image_size_original', 'image_size_compressed')
        }),
        ('Vision Usage (Step 1: Image → Title/Description)', {
            'fields': ('vision_input_tokens', 'vision_output_tokens', 'vision_cost_usd')
        }),
        ('Categorization Usage (Step 2: Text → Category)', {
            'fields': ('categorization_input_tokens', 'categorization_output_tokens', 'categorization_cost_usd')
        }),
        ('Total Usage (Legacy)', {
            'fields': ('input_tokens', 'output_tokens', 'estimated_cost_usd'),
            'classes': ('collapse',)
        }),
        ('AI Suggestions', {
            'fields': ('suggested_category', 'suggested_category_confidence',
                      'suggested_title', 'suggested_description', 'suggested_price',
                      'overall_confidence')
        }),
        ('Outcome Tracking', {
            'fields': ('final_item', 'user_accepted_category', 'user_accepted_title',
                      'user_accepted_price'),
            'classes': ('collapse',)
        }),
        ('Raw Data (Debugging/Transparency)', {
            'fields': ('vision_request_prompt', 'vision_response_raw',
                      'categorization_request_prompt', 'categorization_response_raw'),
            'classes': ('collapse',),
            'description': 'Full AI prompts and responses for debugging and transparency.'
        }),
        ('Errors', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        })
    )

    def profile_link(self, obj):
        if obj.profile:
            return format_html('<a href="/@{}">{}</a>', obj.profile.id, obj.profile.hna)
        return '-'
    profile_link.short_description = 'Profile'

    def confidence_badge(self, obj):
        if obj.overall_confidence >= 0.8:
            color = 'green'
        elif obj.overall_confidence >= 0.6:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{:.0%}</span>',
            color, obj.overall_confidence
        )
    confidence_badge.short_description = 'Confidence'

    def compression_ratio(self, obj):
        if obj.image_size_original and obj.image_size_compressed:
            ratio = (1 - obj.image_size_compressed / obj.image_size_original) * 100
            return f"{ratio:.1f}% reduction"
        return '-'
    compression_ratio.short_description = 'Compression'

    def item_created(self, obj):
        return '✅' if obj.final_item else '⏳'
    item_created.short_description = 'Item'

    def accuracy_badge(self, obj):
        score = obj.accuracy_score
        if score is None:
            return '-'

        if score >= 0.8:
            color = 'green'
        elif score >= 0.5:
            color = 'orange'
        else:
            color = 'red'

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{:.0%}</span>',
            color, score
        )
    accuracy_badge.short_description = 'Accuracy'
    accuracy_badge.admin_order_field = 'final_item'  # Allow sorting

    @admin.display(ordering='processing_time_ms', description='Total ⏱')
    def total_time_display(self, obj):
        """Display total processing time (vision + categorization)"""
        if obj.processing_time_ms is None:
            return '-'
        ms = obj.processing_time_ms
        if ms > 15000:  # slow (>15s)
            color = '#d32f2f'  # red
        elif ms > 10000:  # moderate (>10s)
            color = '#f57c00'  # orange
        else:  # fast
            color = '#388e3c'  # green
        from django.utils.safestring import mark_safe
        return mark_safe(f'<strong style="color: {color};">{ms/1000:.1f}s</strong>')

    @admin.display(ordering='vision_cost_usd', description='Vision $')
    def vision_cost_display(self, obj):
        """Display vision cost with color coding"""
        if obj.vision_cost_usd is None:
            return '-'
        cost = float(obj.vision_cost_usd)
        if cost > 0.015:  # expensive
            color = '#d32f2f'  # red
        elif cost > 0.010:  # moderate
            color = '#f57c00'  # orange
        else:  # cheap
            color = '#388e3c'  # green
        from django.utils.safestring import mark_safe
        return mark_safe(f'<span style="color: {color}; font-weight: bold;">${cost:.4f}</span>')

    @admin.display(ordering='categorization_cost_usd', description='Cat $')
    def categorization_cost_display(self, obj):
        """Display categorization cost with color coding"""
        if obj.categorization_cost_usd is None:
            return '-'
        cost = float(obj.categorization_cost_usd)
        if cost > 0.010:  # expensive
            color = '#d32f2f'  # red
        elif cost > 0.005:  # moderate
            color = '#f57c00'  # orange
        else:  # cheap
            color = '#388e3c'  # green
        from django.utils.safestring import mark_safe
        return mark_safe(f'<span style="color: {color}; font-weight: bold;">${cost:.4f}</span>')

    @admin.display(ordering='estimated_cost_usd', description='Total $')
    def total_cost_display(self, obj):
        """Display total cost with bold formatting"""
        if obj.estimated_cost_usd is None:
            return '-'
        cost = float(obj.estimated_cost_usd)
        if cost > 0.025:  # expensive
            color = '#d32f2f'  # red
        elif cost > 0.015:  # moderate
            color = '#f57c00'  # orange
        else:  # cheap
            color = '#388e3c'  # green
        from django.utils.safestring import mark_safe
        return mark_safe(f'<strong style="color: {color};">${cost:.4f}</strong>')

    @admin.display(ordering='vision_processing_time_ms', description='Vision ⏱')
    def vision_time_display(self, obj):
        """Display vision processing time"""
        if obj.vision_processing_time_ms is None:
            return '-'
        ms = obj.vision_processing_time_ms
        if ms > 8000:  # slow
            color = '#d32f2f'
        elif ms > 5000:  # moderate
            color = '#f57c00'
        else:  # fast
            color = '#388e3c'
        from django.utils.safestring import mark_safe
        return mark_safe(f'<span style="color: {color};">{ms/1000:.1f}s</span>')

    @admin.display(ordering='categorization_processing_time_ms', description='Cat ⏱')
    def categorization_time_display(self, obj):
        """Display categorization processing time"""
        if obj.categorization_processing_time_ms is None:
            return '-'
        ms = obj.categorization_processing_time_ms
        if ms > 8000:  # slow
            color = '#d32f2f'
        elif ms > 5000:  # moderate
            color = '#f57c00'
        else:  # fast
            color = '#388e3c'
        from django.utils.safestring import mark_safe
        return mark_safe(f'<span style="color: {color};">{ms/1000:.1f}s</span>')

    def has_add_permission(self, request):
        # Logs are created automatically
        return False


@admin.register(QuotaUsageLog)
class QuotaUsageLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'account_display', 'resource_type', 'amount', 'used_at', 'metadata_display')
    list_filter = ('resource_type', 'used_at')
    search_fields = ('account__username', 'account__email')
    readonly_fields = ('account', 'resource_type', 'used_at', 'amount', 'metadata')
    date_hierarchy = 'used_at'
    ordering = ('-used_at',)

    def account_display(self, obj):
        """Display account username"""
        return obj.account.username
    account_display.short_description = 'Account'
    account_display.admin_order_field = 'account__username'

    def metadata_display(self, obj):
        """Display metadata in compact format"""
        if not obj.metadata:
            return '-'
        # Show AI log_id if present
        if 'log_id' in obj.metadata:
            return f"AI Log #{obj.metadata['log_id']}"
        return str(obj.metadata)[:50]
    metadata_display.short_description = 'Context'

    def has_add_permission(self, request):
        # Logs are created automatically
        return False

    def has_change_permission(self, request, obj=None):
        # Read-only logs
        return False


@admin.register(ZenithSettings)
class ZenithSettingsAdmin(admin.ModelAdmin):
    list_display = ('profile', 'enabled', 'gitea_repo_name', 'allow_contacts_access', 'total_queries', 'updated_at')
    list_filter = ('enabled', 'allow_contacts_access')
    search_fields = ('profile__hna', 'profile__display_name')
    readonly_fields = ('total_queries', 'created_at', 'updated_at')

    fieldsets = (
        ('Profile', {
            'fields': ('profile', 'enabled')
        }),
        ('Knowledge Base', {
            'fields': ('gitea_repo_name',),
            'description': 'Gitea repository containing Markdown files with user knowledge.'
        }),
        ('AI Configuration', {
            'fields': ('gemini_api_key', 'system_prompt'),
            'description': 'Personal Gemini API key (optional). If empty, uses global AISettings.'
        }),
        ('Access Control', {
            'fields': ('allow_contacts_access',),
            'description': 'Who can ask questions to this Zenith.'
        }),
        ('Statistics', {
            'fields': ('total_queries', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(ZenithQueryLog)
class ZenithQueryLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'zenith_owner', 'querier_display', 'question_short',
                   'success', 'processing_time_display', 'cost_display')
    list_filter = ('success', 'created_at', 'zenith_owner')
    search_fields = ('zenith_owner__hna', 'querier__hna', 'question', 'answer')
    readonly_fields = ('zenith_owner', 'querier', 'question', 'answer', 'files_used',
                      'processing_time_ms', 'input_tokens', 'output_tokens',
                      'estimated_cost_usd', 'error_message', 'success', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('Query', {
            'fields': ('created_at', 'zenith_owner', 'querier', 'question', 'answer')
        }),
        ('Context', {
            'fields': ('files_used',),
            'classes': ('collapse',)
        }),
        ('Performance', {
            'fields': ('processing_time_ms', 'input_tokens', 'output_tokens', 'estimated_cost_usd')
        }),
        ('Status', {
            'fields': ('success', 'error_message'),
            'classes': ('collapse',)
        })
    )

    def querier_display(self, obj):
        if obj.querier:
            return obj.querier.hna
        return "(self)"
    querier_display.short_description = 'Querier'

    def question_short(self, obj):
        return obj.question[:80] + '...' if len(obj.question) > 80 else obj.question
    question_short.short_description = 'Question'

    @admin.display(ordering='processing_time_ms', description='Time')
    def processing_time_display(self, obj):
        if obj.processing_time_ms is None:
            return '-'
        ms = obj.processing_time_ms
        return f'{ms/1000:.1f}s'

    @admin.display(ordering='estimated_cost_usd', description='Cost')
    def cost_display(self, obj):
        if obj.estimated_cost_usd is None:
            return '-'
        return f'${float(obj.estimated_cost_usd):.4f}'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TranslationLog)
class TranslationLogAdmin(admin.ModelAdmin):
    """Read-only ledger of machine-translation spend.

    The changelist header carries the running total for the current filter, so
    "what has translation cost me" is answerable without exporting anything.
    """
    list_display = ('id', 'created_at', 'langs', 'target_object', 'model_name',
                    'source_chars', 'input_tokens', 'output_tokens', 'cost',
                    'duration_ms', 'success')
    list_display_links = ('id', 'created_at')
    list_filter = ('success', 'target_lang', 'source_lang', 'model_name', 'object_type', 'created_at')
    search_fields = ('object_id', 'error_message')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'model_name', 'source_lang', 'target_lang',
                       'object_type', 'object_id', 'field_name', 'source_chars',
                       'is_html', 'input_tokens', 'output_tokens', 'cost_usd',
                       'duration_ms', 'success', 'error_message')

    @admin.display(description='Direction', ordering='target_lang')
    def langs(self, obj):
        return f"{obj.source_lang} → {obj.target_lang}"

    @admin.display(description='Cost USD', ordering='cost_usd')
    def cost(self, obj):
        # See AIUsageLogAdmin.cost — the admin localises decimals, and a decimal
        # comma on a USD figure reads as a thousands separator.
        return f"${obj.cost_usd:.6f}"

    @admin.display(description='Translated')
    def target_object(self, obj):
        if not obj.object_type:
            return '—'
        return f"{obj.object_type}.{obj.field_name} {obj.object_id}"

    def changelist_view(self, request, extra_context=None):
        """Totals for whatever the current filter selects."""
        from django.db.models import Sum
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
        totals = qs.aggregate(cost=Sum('cost_usd'), tin=Sum('input_tokens'),
                              tout=Sum('output_tokens'))
        response.context_data['title'] = (
            f"Translation Logs — ${totals['cost'] or 0:.4f} "
            f"({totals['tin'] or 0} in / {totals['tout'] or 0} out tokens)")
        return response

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    """Read-only ledger for the paths without one of their own — image
    generation, the ID-photo validator, the voice bot.

    The changelist header carries the running total for the current filter, so
    "what has the illustration button cost me" is one filter away.
    """
    # Cost sits early: with the filter sidebar open the tail of a wide changelist
    # scrolls out of view, and cost is the column this page exists for.
    list_display = ('id', 'created_at', 'kind', 'model_name', 'cost',
                    'billed_units', 'input_tokens', 'output_tokens', 'image_tokens',
                    'success', 'profile')
    list_display_links = ('id', 'created_at')
    list_filter = ('kind', 'success', 'model_name', 'created_at')
    # `hna` is a computed property, not a column — search the stored name.
    search_fields = ('error_message', 'profile__local_name')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'kind', 'model_name', 'profile', 'input_tokens',
                       'output_tokens', 'image_tokens', 'units', 'unit_kind', 'cost_usd',
                       'duration_ms', 'success', 'error_message', 'meta')

    @admin.display(description='Units', ordering='units')
    def billed_units(self, obj):
        if not obj.unit_kind:
            return '—'
        return f"{obj.units:g} {obj.unit_kind}"

    @admin.display(description='Cost USD', ordering='cost_usd')
    def cost(self, obj):
        # Formatted here rather than left to the field: the admin localises
        # decimals, and a ru/pt session renders $0.010526 as "0,010526" — a
        # decimal comma that reads as a thousands separator on a USD figure.
        return f"${obj.cost_usd:.6f}"

    def changelist_view(self, request, extra_context=None):
        """Totals for whatever the current filter selects."""
        from django.db.models import Count, Sum
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
        totals = qs.aggregate(cost=Sum('cost_usd'), calls=Count('id'))
        response.context_data['title'] = (
            f"AI Usage Logs — ${totals['cost'] or 0:.4f} over {totals['calls'] or 0} calls")
        return response

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# Every path that can spend money on a model without writing a ledger row. Empty
# is the correct state: a new paid call site writes to `AIUsageLog` instead of
# being listed here. Anything that does land here is named on the dashboard so
# its total is never read as "all AI spend".
_UNMETERED_AI_PATHS = []


@admin.register(AISpend)
class AISpendAdmin(admin.ModelAdmin):
    """Daily AI spend across every metered path, in one table.

    Replaces the changelist wholesale — the proxy's own rows are irrelevant here;
    the page is an aggregate over three unrelated ledgers.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from collections import OrderedDict
        from datetime import timedelta
        from decimal import Decimal
        from django.db.models import Sum, Count, DecimalField, IntegerField, Value
        from django.db.models.functions import Coalesce, TruncDate
        from django.template.response import TemplateResponse
        from django.utils import timezone

        try:
            days = max(1, min(365, int(request.GET.get('days', 30))))
        except (TypeError, ValueError):
            days = 30
        since = timezone.now() - timedelta(days=days)

        money = DecimalField(max_digits=14, decimal_places=6)
        zero_money = Value(Decimal('0'), output_field=money)
        zero_int = Value(0, output_field=IntegerField())

        def by_day(qs, cost_expr, in_expr, out_expr):
            return (qs.filter(created_at__gte=since)
                      .annotate(day=TruncDate('created_at'))
                      .values('day')
                      .annotate(calls=Count('id'), cost=Sum(cost_expr),
                                tin=Sum(in_expr), tout=Sum(out_expr))
                      .order_by())

        # An analysis bills two models (vision + categorization), so a row's cost
        # is the pair. Rows written before that split carry only the legacy
        # `estimated_cost_usd`/`input_tokens` fields — fall back to those rather
        # than reporting the old rows as free.
        sources = OrderedDict()
        sources['Vision + categorization'] = by_day(
            AIAnalysisLog.objects.all(),
            Coalesce('vision_cost_usd', 'estimated_cost_usd', zero_money)
            + Coalesce('categorization_cost_usd', zero_money),
            Coalesce('vision_input_tokens', 'input_tokens', zero_int)
            + Coalesce('categorization_input_tokens', zero_int),
            Coalesce('vision_output_tokens', 'output_tokens', zero_int)
            + Coalesce('categorization_output_tokens', zero_int),
        )
        sources['Zenith'] = by_day(
            ZenithQueryLog.objects.all(),
            Coalesce('estimated_cost_usd', zero_money),
            Coalesce('input_tokens', zero_int), Coalesce('output_tokens', zero_int))
        sources['Translation'] = by_day(
            TranslationLog.objects.all(),
            Coalesce('cost_usd', zero_money),
            Coalesce('input_tokens', zero_int), Coalesce('output_tokens', zero_int))
        # Everything without a ledger of its own: image generation, the ID-photo
        # validator, the voice bot. Image output tokens are counted in the "out"
        # column so a generated illustration is visibly not a text call.
        sources['Images, photo & voice'] = by_day(
            AIUsageLog.objects.all(),
            Coalesce('cost_usd', zero_money),
            Coalesce('input_tokens', zero_int),
            Coalesce('output_tokens', zero_int) + Coalesce('image_tokens', zero_int))

        labels = list(sources)
        rows = {}
        totals = {label: {'calls': 0, 'cost': Decimal('0'), 'tin': 0, 'tout': 0} for label in labels}
        for label, agg in sources.items():
            for entry in agg:
                cell = rows.setdefault(entry['day'], {l: None for l in labels})
                cost = entry['cost'] or Decimal('0')
                # Money is formatted here, not in the template: `floatformat`
                # localises, so a ru/pt admin renders "$0,3057" — a decimal
                # comma that reads as a thousands separator on a USD figure.
                value = {'calls': entry['calls'], 'cost': cost, 'cost_str': f'{cost:.4f}',
                         'tin': entry['tin'] or 0, 'tout': entry['tout'] or 0}
                cell[label] = value
                totals[label]['calls'] += value['calls']
                totals[label]['tin'] += value['tin']
                totals[label]['tout'] += value['tout']
                totals[label]['cost'] += value['cost']

        table = []
        for day in sorted(rows, reverse=True):
            cells = rows[day]
            day_cost = sum((c['cost'] for c in cells.values() if c), Decimal('0'))
            table.append({
                'day': day,
                'cells': [cells[label] for label in labels],
                'cost_str': f'{day_cost:.4f}',
                'calls': sum((c['calls'] for c in cells.values() if c), 0),
            })

        grand_cost = sum((t['cost'] for t in totals.values()), Decimal('0'))
        grand = {
            'cost_str': f'{grand_cost:.4f}',
            'calls': sum(t['calls'] for t in totals.values()),
            'tin': sum(t['tin'] for t in totals.values()),
            'tout': sum(t['tout'] for t in totals.values()),
        }

        context = {
            **self.admin_site.each_context(request),
            'title': f'AI Spend — last {days} days',
            'opts': self.model._meta,
            'labels': labels,
            'table': table,
            'totals': [{**totals[label], 'cost_str': f"{totals[label]['cost']:.4f}"}
                       for label in labels],
            'grand': grand,
            'days': days,
            'day_options': [7, 30, 90, 365],
            'unmetered': _UNMETERED_AI_PATHS,
        }
        return TemplateResponse(request, 'admin/parahub/ai_spend.html', context)
