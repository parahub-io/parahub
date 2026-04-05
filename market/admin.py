from django.contrib import admin
from .models import Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'owner', 'type', 'get_pricing_display', 'is_active', 'created_at']
    list_filter = ['type', 'is_active', 'created_at', 'category']
    search_fields = ['title', 'description', 'owner__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    filter_horizontal = ['tags']

    def get_pricing_display(self, obj):
        """Display pricing options in admin list"""
        if not obj.pricing_options:
            return "No price"

        prices = []
        for opt in obj.pricing_options[:3]:  # Show first 3 options
            if opt.get('type') == 'free':
                price_str = "FREE"
            else:
                price_str = f"{opt.get('amount', 0)} {opt.get('currency', 'EUR')}"
                if opt.get('unit'):
                    price_str += f"/{opt['unit']}"
            prices.append(price_str)

        return ", ".join(prices)
    get_pricing_display.short_description = 'Pricing'


