"""
Django Admin Configuration for Internal Chat
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Thread, ThreadParticipant, Message, GroupSettings,
    Attachment, MessageReaction, DirectThreadKey, AuditLog
)


class ThreadParticipantInline(admin.TabularInline):
    """
    Inline admin for thread participants
    """
    model = ThreadParticipant
    extra = 0
    fields = ['user', 'role', 'is_muted', 'joined_at', 'left_at']
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user']


class GroupSettingsInline(admin.StackedInline):
    """
    Inline admin for group settings
    """
    model = GroupSettings
    extra = 0
    fields = ['posting_mode', 'mentions_enabled', 'reactions_enabled']


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    """
    Admin interface for Thread model
    """
    list_display = [
        'id', 'type', 'title', 'created_by', 'participant_count',
        'is_archived', 'created_at', 'updated_at'
    ]
    list_filter = ['type', 'is_archived', 'created_at']
    search_fields = ['title', 'created_by__username', 'created_by__email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'participant_count']
    inlines = [ThreadParticipantInline, GroupSettingsInline]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'type', 'title', 'avatar', 'is_archived')
        }),
        ('Metadata', {
            'fields': ('created_by', 'participant_count', 'created_at', 'updated_at')
        }),
    )
    
    actions = ['archive_threads', 'unarchive_threads']
    
    def archive_threads(self, request, queryset):
        count = queryset.update(is_archived=True)
        self.message_user(request, f'{count} thread(s) archived successfully')
    archive_threads.short_description = 'Archive selected threads'
    
    def unarchive_threads(self, request, queryset):
        count = queryset.update(is_archived=False)
        self.message_user(request, f'{count} thread(s) unarchived successfully')
    unarchive_threads.short_description = 'Unarchive selected threads'


@admin.register(ThreadParticipant)
class ThreadParticipantAdmin(admin.ModelAdmin):
    """
    Admin interface for ThreadParticipant model
    """
    list_display = [
        'id', 'thread', 'user', 'role', 'is_muted',
        'joined_at', 'is_active'
    ]
    list_filter = ['role', 'is_muted', 'joined_at']
    search_fields = ['user__username', 'user__email', 'thread__title']
    readonly_fields = ['joined_at']
    autocomplete_fields = ['thread', 'user']
    date_hierarchy = 'joined_at'
    
    def is_active(self, obj):
        return obj.left_at is None
    is_active.boolean = True


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """
    Admin interface for Message model
    """
    list_display = [
        'id', 'thread', 'sender', 'content_preview',
        'has_attachments', 'is_deleted', 'created_at'
    ]
    list_filter = ['has_attachments', 'created_at']
    search_fields = ['content', 'sender__username', 'thread__title']
    readonly_fields = ['id', 'created_at', 'edited_at', 'deleted_at']
    autocomplete_fields = ['thread', 'sender', 'reply_to']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Message Content', {
            'fields': ('thread', 'sender', 'content', 'reply_to')
        }),
        ('Attachments', {
            'fields': ('has_attachments',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'edited_at', 'deleted_at')
        }),
    )
    
    def content_preview(self, obj):
        preview = obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
        return preview
    content_preview.short_description = 'Content'
    
    def is_deleted(self, obj):
        return obj.deleted_at is not None
    is_deleted.boolean = True
    
    actions = ['soft_delete_messages', 'hard_delete_messages']
    
    def soft_delete_messages(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(deleted_at__isnull=True).update(deleted_at=timezone.now())
        self.message_user(request, f'{count} message(s) soft deleted successfully')
    soft_delete_messages.short_description = 'Soft delete selected messages'
    
    def hard_delete_messages(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'{count} message(s) permanently deleted')
    hard_delete_messages.short_description = 'Permanently delete selected messages'


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    """
    Admin interface for MessageReaction model
    """
    list_display = ['id', 'message', 'user', 'emoji', 'created_at']
    list_filter = ['emoji', 'created_at']
    search_fields = ['user__username', 'message__content']
    readonly_fields = ['created_at']
    autocomplete_fields = ['message', 'user']
    date_hierarchy = 'created_at'


@admin.register(GroupSettings)
class GroupSettingsAdmin(admin.ModelAdmin):
    """
    Admin interface for GroupSettings model
    """
    list_display = [
        'id', 'thread', 'posting_mode', 'mentions_enabled',
        'reactions_enabled', 'updated_at'
    ]
    list_filter = ['posting_mode', 'mentions_enabled', 'reactions_enabled']
    search_fields = ['thread__title']
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['thread']


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    """
    Admin interface for Attachment model
    """
    list_display = [
        'id', 'file_name', 'content_type', 'size_mb',
        'message', 'created_at'
    ]
    list_filter = ['content_type', 'created_at']
    search_fields = ['file_name', 'message__content']
    readonly_fields = ['id', 'size', 'size_mb', 'checksum', 'created_at']
    autocomplete_fields = ['message']
    date_hierarchy = 'created_at'
    
    def size_mb(self, obj):
        return f"{obj.size_mb} MB"
    size_mb.short_description = 'Size'


@admin.register(DirectThreadKey)
class DirectThreadKeyAdmin(admin.ModelAdmin):
    """
    Admin interface for DirectThreadKey model
    """
    list_display = ['id', 'user_low_id', 'user_high_id', 'thread']
    search_fields = ['user_low_id', 'user_high_id', 'thread__id']
    readonly_fields = ['user_low_id', 'user_high_id']
    autocomplete_fields = ['thread']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin interface for AuditLog model
    """
    list_display = [
        'id', 'action', 'actor', 'thread',
        'target_user', 'created_at'
    ]
    list_filter = ['action', 'created_at']
    search_fields = [
        'actor__username', 'target_user__username',
        'thread__title'
    ]
    readonly_fields = ['id', 'created_at', 'metadata']
    autocomplete_fields = ['actor', 'thread', 'target_user']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Action Details', {
            'fields': ('action', 'actor', 'thread', 'target_user')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Audit logs should not be manually created
        return False
    
    def has_change_permission(self, request, obj=None):
        # Audit logs should not be edited
        return False
