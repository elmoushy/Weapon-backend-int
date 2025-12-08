"""
Django Admin configuration for quicklinks app.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import QuickLink, UserQuickLinkPreference


@admin.register(QuickLink)
class QuickLinkAdmin(admin.ModelAdmin):
    """Admin interface for Quick Links"""
    
    list_display = [
        'name',
        'position',
        'is_active',
        'has_icon_display',
        'redirect_url_truncated',
        'created_at',
    ]
    
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'redirect_url']
    ordering = ['position', '-created_at']
    
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'icon_preview']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'redirect_url', 'position', 'is_active')
        }),
        ('Icon', {
            'fields': ('icon_preview', 'icon_original_filename', 'icon_mime_type'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def has_icon_display(self, obj):
        """Display icon status"""
        if obj.has_icon:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: gray;">✗</span>')
    has_icon_display.short_description = 'Icon'
    
    def redirect_url_truncated(self, obj):
        """Display truncated URL"""
        if len(obj.redirect_url) > 50:
            return f"{obj.redirect_url[:50]}..."
        return obj.redirect_url
    redirect_url_truncated.short_description = 'Redirect URL'
    
    def icon_preview(self, obj):
        """Display icon preview if available"""
        if obj.has_icon and obj.icon_mime_type:
            return format_html(
                '<span>Icon uploaded: {} ({})</span>',
                obj.icon_original_filename or 'unknown',
                obj.icon_mime_type
            )
        return "No icon uploaded"
    icon_preview.short_description = 'Icon Preview'


@admin.register(UserQuickLinkPreference)
class UserQuickLinkPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for User Quick Link Preferences"""
    
    list_display = [
        'user',
        'quicklink',
        'is_pinned',
        'pin_order',
        'click_count',
        'last_accessed_at',
    ]
    
    list_filter = ['is_pinned', 'created_at']
    search_fields = ['user__email', 'quicklink__name']
    ordering = ['user', '-is_pinned', 'pin_order', '-last_accessed_at']
    
    readonly_fields = ['created_at', 'updated_at']
    
    raw_id_fields = ['user', 'quicklink']
