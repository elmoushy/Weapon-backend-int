"""
Django admin configuration for newsletters system.
"""

from django.contrib import admin
from .models import Newsletter, NewsletterImage


class NewsletterImageInline(admin.TabularInline):
    """Inline admin for newsletter images"""
    model = NewsletterImage
    extra = 0
    fields = ['original_filename', 'is_main', 'display_order', 'file_size', 'uploaded_at']
    readonly_fields = ['original_filename', 'file_size', 'uploaded_at']
    can_delete = True


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    """Admin interface for Newsletter model"""
    
    list_display = ['id', 'news_type', 'title', 'author', 'created_at', 'image_count']
    list_filter = ['news_type', 'created_at', 'author']
    search_fields = ['title', 'details', 'author__username']
    readonly_fields = ['created_at', 'updated_at', 'title_hash', 'details_hash']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('news_type', 'title', 'details')
        }),
        ('Author', {
            'fields': ('author',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'title_hash', 'details_hash'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [NewsletterImageInline]
    
    def image_count(self, obj):
        """Display number of images"""
        return obj.images.count()
    image_count.short_description = 'Images'
    
    def save_model(self, request, obj, form, change):
        """Set author to current user if creating new newsletter"""
        if not change:  # Creating new object
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(NewsletterImage)
class NewsletterImageAdmin(admin.ModelAdmin):
    """Admin interface for NewsletterImage model"""
    
    list_display = ['id', 'newsletter', 'original_filename', 'is_main', 'display_order', 'file_size', 'uploaded_at']
    list_filter = ['is_main', 'uploaded_at', 'newsletter__news_type']
    search_fields = ['original_filename', 'newsletter__title']
    readonly_fields = ['uploaded_at', 'file_size', 'mime_type']
    
    fieldsets = (
        ('Newsletter', {
            'fields': ('newsletter',)
        }),
        ('File Information', {
            'fields': ('original_filename', 'file_size', 'mime_type', 'uploaded_at')
        }),
        ('Display Settings', {
            'fields': ('is_main', 'display_order')
        }),
    )
