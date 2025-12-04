"""
Internal Chat Models
Supports Oracle, SQL Server, and SQLite with optimized indexes
"""
import uuid
import logging
from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from .managers import (
    ThreadManager, MessageManager, ThreadParticipantManager, AttachmentManager
)

logger = logging.getLogger(__name__)


class Thread(models.Model):
    """
    Conversation thread (direct or group chat)
    """
    TYPE_DIRECT = 'direct'
    TYPE_GROUP = 'group'
    TYPE_CHOICES = [
        (TYPE_DIRECT, 'Direct'),
        (TYPE_GROUP, 'Group'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    avatar = models.ImageField(upload_to='chat/avatars/', null=True, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_threads'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = ThreadManager()
    
    class Meta:
        db_table = 'internal_chat_thread'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['type', 'created_at']),
            models.Index(fields=['created_by', 'created_at']),
        ]
    
    def __str__(self):
        if self.type == self.TYPE_DIRECT:
            return f"Direct chat {self.id}"
        return self.title or f"Group chat {self.id}"
    
    @property
    def participant_count(self):
        return self.participants.filter(left_at__isnull=True).count()


class ThreadParticipant(models.Model):
    """
    User participation in a thread with role
    """
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MEMBER, 'Member'),
    ]
    
    id = models.AutoField(primary_key=True)
    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='thread_participations'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER, db_index=True)
    is_muted = models.BooleanField(default=False)
    unread_count = models.IntegerField(default=0, db_index=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    
    objects = ThreadParticipantManager()
    
    class Meta:
        db_table = 'internal_chat_participant'
        unique_together = [['thread', 'user']]
        indexes = [
            models.Index(fields=['thread', 'user']),
            models.Index(fields=['user', 'joined_at']),
            models.Index(fields=['thread', 'role']),
            models.Index(fields=['user', 'unread_count']),
        ]
    
    def __str__(self):
        return f"{self.user.username} in {self.thread} ({self.role})"
    
    def is_active(self):
        """Check if participant is still active in thread"""
        return self.left_at is None


class Message(models.Model):
    """
    Chat message with soft delete support
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages'
    )
    content = models.TextField()
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )
    has_attachments = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    objects = MessageManager()
    
    class Meta:
        db_table = 'internal_chat_message'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['thread', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['thread', 'deleted_at', 'created_at']),
        ]
    
    def __str__(self):
        preview = self.content[:50] + '...' if len(self.content) > 50 else self.content
        return f"Message from {self.sender}: {preview}"
    
    def is_deleted(self):
        """Check if message is soft deleted"""
        return self.deleted_at is not None
    
    def soft_delete(self):
        """Soft delete the message"""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


class MessageReaction(models.Model):
    """
    Emoji reactions to messages
    """
    id = models.AutoField(primary_key=True)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_reactions'
    )
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'internal_chat_reaction'
        unique_together = [['message', 'user']]
        indexes = [
            models.Index(fields=['message', 'emoji']),
            models.Index(fields=['message', 'user']),
        ]
    
    def __str__(self):
        return f"{self.emoji} by {self.user.username} on message {self.message.id}"


class GroupSettings(models.Model):
    """
    Settings for group threads
    """
    POSTING_MODE_ALL = 'all'
    POSTING_MODE_ADMINS_ONLY = 'admins_only'
    POSTING_MODE_CHOICES = [
        (POSTING_MODE_ALL, 'All Members'),
        (POSTING_MODE_ADMINS_ONLY, 'Admins Only'),
    ]
    
    id = models.AutoField(primary_key=True)
    thread = models.OneToOneField(
        Thread,
        on_delete=models.CASCADE,
        related_name='group_settings'
    )
    posting_mode = models.CharField(
        max_length=15,
        choices=POSTING_MODE_CHOICES,
        default=POSTING_MODE_ALL
    )
    members_can_add_others = models.BooleanField(
        default=False,
        help_text='Allow regular members to add new participants to the group'
    )
    mentions_enabled = models.BooleanField(default=True)
    reactions_enabled = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_group_settings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'internal_chat_group_settings'
        verbose_name_plural = 'Group Settings'
    
    def __str__(self):
        return f"Settings for {self.thread}"


class Attachment(models.Model):
    """
    File attachments for messages - stored as blobs in database
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments',
        null=True,
        blank=True
    )
    # Store file content as blob in database
    file_data = models.BinaryField(null=True, blank=True)
    file_name = models.CharField(max_length=255)  # Stores sanitized original filename
    content_type = models.CharField(max_length=100)
    size = models.BigIntegerField()  # Size in bytes
    caption = models.TextField(blank=True, null=True)  # Optional caption/comment
    checksum = models.CharField(max_length=64, null=True, blank=True)  # SHA256
    created_at = models.DateTimeField(auto_now_add=True)
    
    objects = AttachmentManager()
    
    class Meta:
        db_table = 'internal_chat_attachment'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['message', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.file_name} ({self.size} bytes)"
    
    @property
    def size_mb(self):
        """Return size in megabytes"""
        return round(self.size / (1024 * 1024), 2)


class DirectThreadKey(models.Model):
    """
    Enforces uniqueness of direct threads between two users
    """
    id = models.AutoField(primary_key=True)
    user_low_id = models.IntegerField(db_index=True)
    user_high_id = models.IntegerField(db_index=True)
    thread = models.OneToOneField(
        Thread,
        on_delete=models.CASCADE,
        related_name='direct_key'
    )
    
    class Meta:
        db_table = 'internal_chat_direct_thread_key'
        unique_together = [['user_low_id', 'user_high_id']]
        indexes = [
            models.Index(fields=['user_low_id', 'user_high_id']),
        ]
    
    def __str__(self):
        return f"Direct thread key: {self.user_low_id} <-> {self.user_high_id}"
    
    @staticmethod
    def get_or_create_thread(user1, user2):
        """
        Get or create a direct thread between two users
        Returns: (thread, created)
        """
        from django.utils import timezone
        
        # Ensure consistent ordering
        user_low_id = min(user1.id, user2.id)
        user_high_id = max(user1.id, user2.id)
        
        try:
            key = DirectThreadKey.objects.select_related('thread').get(
                user_low_id=user_low_id,
                user_high_id=user_high_id
            )
            thread = key.thread
            
            # Re-activate participants if they left
            for user in [user1, user2]:
                participant = ThreadParticipant.objects.filter(
                    thread=thread,
                    user=user
                ).first()
                
                if participant and participant.left_at is not None:
                    # Re-join the thread
                    participant.left_at = None
                    participant.joined_at = timezone.now()
                    participant.save()
            
            return thread, False
        except DirectThreadKey.DoesNotExist:
            # Create new thread
            from .services import ThreadService
            thread = ThreadService.create_direct_thread(user1, user2)
            return thread, True


class AuditLog(models.Model):
    """
    Audit trail for thread operations
    """
    ACTION_MEMBER_ADDED = 'member_added'
    ACTION_MEMBER_REMOVED = 'member_removed'
    ACTION_ROLE_CHANGED = 'role_changed'
    ACTION_SETTINGS_CHANGED = 'settings_changed'
    ACTION_THREAD_CREATED = 'thread_created'
    ACTION_THREAD_DELETED = 'thread_deleted'
    ACTION_MESSAGE_DELETED = 'message_deleted'
    
    ACTION_CHOICES = [
        (ACTION_MEMBER_ADDED, 'Member Added'),
        (ACTION_MEMBER_REMOVED, 'Member Removed'),
        (ACTION_ROLE_CHANGED, 'Role Changed'),
        (ACTION_SETTINGS_CHANGED, 'Settings Changed'),
        (ACTION_THREAD_CREATED, 'Thread Created'),
        (ACTION_THREAD_DELETED, 'Thread Deleted'),
        (ACTION_MESSAGE_DELETED, 'Message Deleted'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='chat_actions'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_audit_targets'
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'internal_chat_audit_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['thread', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} by {self.actor} at {self.created_at}"
