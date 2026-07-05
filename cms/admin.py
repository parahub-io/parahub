from django.contrib import admin
from .models import Post, Site, SitePage


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'establishment', 'status', 'language', 'subscribers_only', 'published_at')
    list_filter = ('status', 'language', 'is_pinned', 'subscribers_only')
    search_fields = ('title', 'slug')
    raw_id_fields = ('author', 'establishment', 'translation_of')
    readonly_fields = ('content_html', 'comments_count')


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'accent_color', 'is_active', 'custom_domain')
    list_filter = ('is_active',)
    raw_id_fields = ('profile', 'establishment')
    readonly_fields = ('hero_text_html',)


@admin.register(SitePage)
class SitePageAdmin(admin.ModelAdmin):
    list_display = ('title', 'site', 'slug', 'order', 'show_in_nav', 'is_published')
    list_filter = ('is_published', 'show_in_nav')
    search_fields = ('title', 'slug')
    raw_id_fields = ('site',)
    readonly_fields = ('content_html',)
