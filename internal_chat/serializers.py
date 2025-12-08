"""
DRF Serializers for Internal Chat
"""
from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import (
    Thread, ThreadParticipant, Message, GroupSettings,
    Attachment, MessageReaction, AuditLog
)
from .services import ThreadService
from weaponpowercloud_backend.utils import build_absolute_uri_https, force_https

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """
    Basic user info for chat participants
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = fields


class MessageReactionSerializer(serializers.ModelSerializer):
    """
    Serializer for message reactions
    """
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = MessageReaction
        fields = ['id', 'emoji', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class AttachmentSerializer(serializers.ModelSerializer):
    """
    Serializer for message attachments
    """
    url = serializers.SerializerMethodField()
    size_mb = serializers.ReadOnlyField()
    
    class Meta:
        model = Attachment
        fields = ['id', 'file_name', 'content_type', 'size', 'size_mb', 'url', 'caption', 'created_at']
        read_only_fields = ['id', 'size', 'size_mb', 'created_at']
    
    def get_url(self, obj):
        """
        Return download URL for blob-stored attachment
        """
        request = self.context.get('request')
        if request:
            # Build download URL for blob storage using the router-generated URL
            try:
                from django.urls import reverse
                download_path = reverse('internal_chat:attachment-download', kwargs={'pk': obj.pk})
                return force_https(request.build_absolute_uri(download_path), request)
            except Exception:
                # Fallback: construct URL manually
                return force_https(request.build_absolute_uri(f'/api/internal-chat/attachments/{obj.pk}/download/'), request)
        return None


class AttachmentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for uploading attachments with security validation
    """
    file = serializers.FileField()
    file_name = serializers.CharField(required=False, allow_blank=True)
    caption = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    
    class Meta:
        model = Attachment
        fields = ['id', 'file', 'file_name', 'caption', 'content_type', 'size']
        read_only_fields = ['id', 'size', 'content_type']
    
    def validate_file(self, value):
        """
        Validate uploaded file using magic bytes (not Content-Type header).
        
        This provides defense-in-depth against:
        - File extension spoofing (malware.exe → malware.jpg)
        - MIME type spoofing (claiming image/jpeg for executable)
        - Oversized files (DoS attack via storage exhaustion)
        - Path traversal attacks (../../etc/passwd)
        - Dangerous filenames (CON, PRN, null bytes, etc.)
        """
        from .security_utils import (
            validate_file_type, validate_file_size, sanitize_caption,
            sanitize_filename, validate_filename_extension, ALLOWED_EXTENSIONS
        )
        from django.core.exceptions import ValidationError as DjangoValidationError
        
        # SECURITY: Sanitize original filename FIRST
        original_name = value.name
        
        try:
            sanitized_name = sanitize_filename(original_name)
        except DjangoValidationError as e:
            raise serializers.ValidationError(f"Invalid filename: {str(e)}")
        
        # SECURITY: Validate extension against whitelist
        try:
            validate_filename_extension(sanitized_name, ALLOWED_EXTENSIONS)
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))
        
        # Update file name to sanitized version
        value.name = sanitized_name
        
        # SECURITY: Validate file size (fail fast for large files)
        max_size_mb = getattr(settings, 'INTERNAL_CHAT_MAX_ATTACHMENT_SIZE', 10)
        validate_file_size(value, max_size_mb=max_size_mb)
        
        # SECURITY: Validate file type using magic bytes (not Content-Type header!)
        # This is the CRITICAL security check - detects actual file content
        detected_mime = validate_file_type(value)
        
        # Store for use in create()
        self.context['detected_mime'] = detected_mime
        self.context['sanitized_filename'] = sanitized_name
        
        return value
    
    def validate_caption(self, value):
        """
        Sanitize caption to prevent XSS attacks
        """
        from .security_utils import sanitize_caption
        
        if value:
            return sanitize_caption(value)
        return value
    
    def create(self, validated_data):
        """
        Create attachment with file data stored as blob in database.
        """
        import hashlib
        
        file = validated_data['file']
        
        # Read file content into memory
        file_content = file.read()
        
        # Calculate SHA256 checksum
        checksum = hashlib.sha256(file_content).hexdigest()
        
        # Use sanitized filename from validation (already cleaned)
        sanitized_name = self.context.get('sanitized_filename', file.name)
        
        # Use detected MIME type (from magic bytes) instead of client-provided Content-Type
        detected_mime = self.context.get('detected_mime', file.content_type)
        
        # Create attachment with blob data stored in database
        attachment = Attachment.objects.create(
            message=None,  # Will be set when message is created
            file_data=file_content,
            file_name=sanitized_name,  # Store sanitized original name for display
            caption=validated_data.get('caption', ''),
            content_type=detected_mime,  # Use validated MIME type, not header
            size=len(file_content),
            checksum=checksum
        )
        
        return attachment


class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer for messages (list and detail)
    """
    sender = UserBasicSerializer(read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    reactions = MessageReactionSerializer(many=True, read_only=True)
    reply_to = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()
    is_deleted = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()
    thread_id = serializers.UUIDField(source='thread.id', read_only=True)
    updated_at = serializers.DateTimeField(source='edited_at', read_only=True, allow_null=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'thread_id', 'sender', 'content', 'reply_to',
            'has_attachments', 'attachments', 'reactions',
            'is_edited', 'is_deleted', 'is_read',
            'created_at', 'updated_at', 'edited_at'
        ]
        read_only_fields = [
            'id', 'thread_id', 'sender', 'has_attachments',
            'is_edited', 'is_deleted', 'is_read',
            'created_at', 'updated_at', 'edited_at'
        ]
    
    def get_reply_to(self, obj):
        if obj.reply_to and not obj.reply_to.is_deleted():
            return {
                'id': obj.reply_to.id,
                'content': obj.reply_to.content[:100],
                'sender': UserBasicSerializer(obj.reply_to.sender).data
            }
        return None
    
    def get_is_edited(self, obj):
        return obj.edited_at is not None
    
    def get_is_deleted(self, obj):
        return obj.deleted_at is not None
    
    def get_is_read(self, obj):
        """
        Check if current user has read this message.
        Returns False if no user in context (for WebSocket broadcasts).
        """
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            # For WebSocket messages, default to False
            # The frontend will update read status separately
            return False
        
        user = request.user
        if not user or user.is_anonymous:
            return False
        
        # Check if user has read up to this message
        try:
            participant = ThreadParticipant.objects.get(
                thread=obj.thread,
                user=user,
                left_at__isnull=True
            )
            if participant.last_read_at:
                return obj.created_at <= participant.last_read_at
            return False
        except ThreadParticipant.DoesNotExist:
            return False


class MessageCreateSerializer(serializers.Serializer):
    """
    Serializer for creating messages
    """
    content = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    reply_to = serializers.UUIDField(required=False, allow_null=True)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True
    )
    
    def validate(self, data):
        """
        Validate that either content or attachments are provided
        """
        content = data.get('content', '').strip()
        attachment_ids = data.get('attachment_ids', [])
        
        if not content and not attachment_ids:
            raise serializers.ValidationError(
                "Message must have either content or attachments"
            )
        
        # Store cleaned content
        data['content'] = content
        return data


class MessageUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating messages
    """
    content = serializers.CharField(max_length=10000)
    
    def validate_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Message content cannot be empty")
        return value.strip()


class ThreadParticipantSerializer(serializers.ModelSerializer):
    """
    Serializer for thread participants
    """
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = ThreadParticipant
        fields = [
            'id', 'user', 'role', 'is_muted', 'last_read_at',
            'joined_at', 'unread_count'
        ]
        read_only_fields = ['id', 'user', 'joined_at', 'unread_count']


class GroupSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for group settings
    """
    thread_id = serializers.UUIDField(source='thread.id', read_only=True)
    updated_by = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = GroupSettings
        fields = [
            'thread_id', 'posting_mode', 'members_can_add_others',
            'mentions_enabled', 'reactions_enabled',
            'updated_at', 'updated_by'
        ]
        read_only_fields = ['thread_id', 'updated_at', 'updated_by']
    
    def get_updated_by(self, obj):
        """Return the user who last updated the settings"""
        if obj.updated_by:
            return {
                'id': obj.updated_by.id,
                'first_name': obj.updated_by.first_name,
                'last_name': obj.updated_by.last_name
            }
        return None
    
    def validate_posting_mode(self, value):
        """Validate posting_mode is a valid choice"""
        if value not in [GroupSettings.POSTING_MODE_ALL, GroupSettings.POSTING_MODE_ADMINS_ONLY]:
            raise serializers.ValidationError(
                f"Invalid posting_mode. Must be one of: 'all', 'admins_only'"
            )
        return value


class ThreadSerializer(serializers.ModelSerializer):
    """
    Serializer for threads (list and detail)
    """
    created_by = UserBasicSerializer(read_only=True)
    chat_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    participant_count = serializers.ReadOnlyField()
    my_role = serializers.SerializerMethodField()
    participants = ThreadParticipantSerializer(many=True, read_only=True)
    group_settings = GroupSettingsSerializer(read_only=True)
    
    class Meta:
        model = Thread
        fields = [
            'id', 'type', 'title', 'avatar', 'is_archived',
            'created_by', 'chat_name', 'last_message', 'unread_count',
            'participant_count', 'my_role', 'participants',
            'group_settings', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'type', 'created_by', 'chat_name', 'last_message',
            'unread_count', 'participant_count', 'my_role',
            'created_at', 'updated_at'
        ]
    
    def get_last_message(self, obj):
        # Get from prefetched last_message_list if available
        if hasattr(obj, 'last_message_list') and obj.last_message_list:
            message = obj.last_message_list[0]
            return {
                'id': message.id,
                'sender': UserBasicSerializer(message.sender).data,
                'content': message.content[:100],
                'created_at': message.created_at
            }
        
        # Fallback query
        last_msg = obj.messages.filter(deleted_at__isnull=True).order_by('-created_at').first()
        if last_msg:
            return {
                'id': last_msg.id,
                'sender': UserBasicSerializer(last_msg.sender).data,
                'content': last_msg.content[:100],
                'created_at': last_msg.created_at
            }
        return None
    
    def get_unread_count(self, obj):
        """
        Get unread count for current user from stored field
        """
        user = self.context['request'].user
        try:
            participant = ThreadParticipant.objects.get(
                thread=obj,
                user=user,
                left_at__isnull=True
            )
            return participant.unread_count
        except ThreadParticipant.DoesNotExist:
            return 0
    
    def get_my_role(self, obj):
        user = self.context['request'].user
        try:
            participant = obj.participants.get(user=user, left_at__isnull=True)
            return participant.role
        except ThreadParticipant.DoesNotExist:
            return None
    
    def get_chat_name(self, obj):
        """
        Get display name for the chat:
        - For group chats: return the group title
        - For direct chats: return the other person's full name
        """
        if obj.type == Thread.TYPE_GROUP:
            # For group chats, return the title
            return obj.title
        
        elif obj.type == Thread.TYPE_DIRECT:
            # For direct chats, return the other participant's name
            user = self.context['request'].user
            
            # Get the other participant (not the current user)
            other_participant = obj.participants.filter(
                left_at__isnull=True
            ).exclude(user=user).select_related('user').first()
            
            if other_participant:
                other_user = other_participant.user
                # Return full name if available, otherwise email
                if other_user.first_name or other_user.last_name:
                    return f"{other_user.first_name} {other_user.last_name}".strip()
                return other_user.email
            
            return "Unknown User"
        
        return None


class ThreadCreateSerializer(serializers.Serializer):
    """
    Serializer for creating threads
    """
    type = serializers.ChoiceField(choices=['direct', 'group'])
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1
    )
    
    def validate(self, data):
        if data['type'] == 'direct':
            if len(data['participant_ids']) != 1:
                raise serializers.ValidationError({
                    'participant_ids': "Direct thread must have exactly 1 other participant"
                })
        elif data['type'] == 'group':
            if not data.get('title'):
                raise serializers.ValidationError({
                    'title': "Group thread must have a title"
                })
        
        return data


class ThreadUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating threads
    """
    class Meta:
        model = Thread
        fields = ['title', 'avatar']


class AddMembersSerializer(serializers.Serializer):
    """
    Serializer for adding members to thread
    """
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1
    )


class ChangeRoleSerializer(serializers.Serializer):
    """
    Serializer for changing member role
    """
    role = serializers.ChoiceField(choices=['admin', 'member'])


class ReactionSerializer(serializers.Serializer):
    """
    Serializer for adding reactions
    """
    emoji = serializers.CharField(max_length=10)
    
    def validate_emoji(self, value):
        # Basic emoji validation
        if not value or len(value) > 10:
            raise serializers.ValidationError("Invalid emoji")
        return value


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer for audit logs
    """
    actor = UserBasicSerializer(read_only=True)
    target_user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor', 'action', 'thread', 'target_user',
            'metadata', 'created_at'
        ]
        read_only_fields = fields
