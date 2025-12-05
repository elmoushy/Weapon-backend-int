"""
Business Logic Services for Internal Chat
"""
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import (
    Thread, ThreadParticipant, Message, GroupSettings,
    Attachment, DirectThreadKey, AuditLog, MessageReaction
)
from .security_utils import sanitize_message_content, sanitize_caption, validate_emoji

logger = logging.getLogger(__name__)


class ThreadService:
    """
    Service for thread-related operations
    """
    
    @staticmethod
    @transaction.atomic
    def create_thread(creator, thread_type, title=None, participant_ids=None):
        """
        Create a new thread (direct or group)
        
        Args:
            creator: User creating the thread
            thread_type: 'direct' or 'group'
            title: Thread title (required for group)
            participant_ids: List of user IDs to add
        
        Returns:
            Thread instance
        """
        if thread_type not in [Thread.TYPE_DIRECT, Thread.TYPE_GROUP]:
            raise ValidationError("Invalid thread type")
        
        if thread_type == Thread.TYPE_DIRECT:
            if not participant_ids or len(participant_ids) != 1:
                raise ValidationError("Direct thread must have exactly 1 other participant")
            
            # Check if user is trying to create thread with themselves
            if participant_ids[0] == creator.id:
                raise ValidationError("Cannot create direct thread with yourself")
            
            # Use DirectThreadKey to ensure uniqueness
            from django.contrib.auth import get_user_model
            User = get_user_model()
            other_user = User.objects.get(id=participant_ids[0])
            thread, created = DirectThreadKey.get_or_create_thread(creator, other_user)
            
            if not created:
                logger.info(f"Reusing existing direct thread {thread.id} between users {creator.id} and {other_user.id}")
            
            return thread
        
        # Group thread
        if not title:
            raise ValidationError("Group thread must have a title")
        
        thread = Thread.objects.create(
            type=thread_type,
            title=title,
            created_by=creator
        )
        
        # Add creator as owner
        ThreadParticipant.objects.create(
            thread=thread,
            user=creator,
            role=ThreadParticipant.ROLE_OWNER
        )
        
        # Add other participants as members
        if participant_ids:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            users = User.objects.filter(id__in=participant_ids)
            for user in users:
                if user.id != creator.id:  # Don't add creator twice
                    ThreadParticipant.objects.create(
                        thread=thread,
                        user=user,
                        role=ThreadParticipant.ROLE_MEMBER
                    )
        
        # Create group settings
        from django.conf import settings
        posting_mode = getattr(settings, 'DEFAULT_GROUP_POSTING_MODE', 'all')
        GroupSettings.objects.create(
            thread=thread,
            posting_mode=posting_mode
        )
        
        # Audit log
        AuditLog.objects.create(
            actor=creator,
            action=AuditLog.ACTION_THREAD_CREATED,
            thread=thread,
            metadata={'title': title, 'participant_count': len(participant_ids or []) + 1}
        )
        
        logger.info(f"Created {thread_type} thread {thread.id} by user {creator.id}")
        return thread
    
    @staticmethod
    @transaction.atomic
    def create_direct_thread(user1, user2):
        """
        Create a direct thread between two users
        This is called internally by DirectThreadKey
        """
        thread = Thread.objects.create(
            type=Thread.TYPE_DIRECT,
            created_by=user1
        )
        
        # Add both users as members
        ThreadParticipant.objects.create(
            thread=thread,
            user=user1,
            role=ThreadParticipant.ROLE_MEMBER
        )
        ThreadParticipant.objects.create(
            thread=thread,
            user=user2,
            role=ThreadParticipant.ROLE_MEMBER
        )
        
        # Create DirectThreadKey
        user_low_id = min(user1.id, user2.id)
        user_high_id = max(user1.id, user2.id)
        DirectThreadKey.objects.create(
            user_low_id=user_low_id,
            user_high_id=user_high_id,
            thread=thread
        )
        
        logger.info(f"Created direct thread {thread.id} between users {user1.id} and {user2.id}")
        return thread
    
    @staticmethod
    @transaction.atomic
    def add_participants(thread, user_ids, added_by):
        """
        Add participants to a thread
        """
        # Check permission
        if not ValidationService.can_manage_members(added_by, thread):
            raise PermissionDenied("You don't have permission to add members")
        
        if thread.type == Thread.TYPE_DIRECT:
            raise ValidationError("Cannot add participants to direct thread")
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.filter(id__in=user_ids)
        added_users = []
        
        for user in users:
            # Check if already a participant
            existing = ThreadParticipant.objects.filter(
                thread=thread,
                user=user
            ).first()
            
            if existing and existing.left_at is None:
                continue  # Already active participant
            elif existing and existing.left_at is not None:
                # Re-join
                existing.left_at = None
                existing.joined_at = timezone.now()
                existing.save()
                added_users.append(user)
            else:
                # New participant
                ThreadParticipant.objects.create(
                    thread=thread,
                    user=user,
                    role=ThreadParticipant.ROLE_MEMBER
                )
                added_users.append(user)
            
            # Audit log
            AuditLog.objects.create(
                actor=added_by,
                action=AuditLog.ACTION_MEMBER_ADDED,
                thread=thread,
                target_user=user
            )
        
        logger.info(f"Added {len(added_users)} participants to thread {thread.id} by user {added_by.id}")
        return added_users
    
    @staticmethod
    @transaction.atomic
    def remove_participant(thread, user_id, removed_by):
        """
        Remove a participant from a thread
        """
        # Check permission
        if not ValidationService.can_manage_members(removed_by, thread):
            raise PermissionDenied("You don't have permission to remove members")
        
        if thread.type == Thread.TYPE_DIRECT:
            raise ValidationError("Cannot remove participants from direct thread")
        
        participant = ThreadParticipant.objects.get(
            thread=thread,
            user_id=user_id,
            left_at__isnull=True
        )
        
        # Cannot remove owner
        if participant.role == ThreadParticipant.ROLE_OWNER:
            raise ValidationError("Cannot remove thread owner")
        
        # Soft delete
        participant.left_at = timezone.now()
        participant.save()
        
        # Audit log
        AuditLog.objects.create(
            actor=removed_by,
            action=AuditLog.ACTION_MEMBER_REMOVED,
            thread=thread,
            target_user=participant.user
        )
        
        logger.info(f"Removed user {user_id} from thread {thread.id} by user {removed_by.id}")
    
    @staticmethod
    @transaction.atomic
    def change_participant_role(thread, user_id, new_role, changed_by):
        """
        Change a participant's role
        """
        if not ValidationService.can_manage_members(changed_by, thread):
            raise PermissionDenied("You don't have permission to change roles")
        
        participant = ThreadParticipant.objects.get(
            thread=thread,
            user_id=user_id,
            left_at__isnull=True
        )
        
        # Cannot change owner role (must transfer ownership)
        if participant.role == ThreadParticipant.ROLE_OWNER:
            raise ValidationError("Use transfer_ownership to change owner")
        
        old_role = participant.role
        participant.role = new_role
        participant.save()
        
        # Audit log
        AuditLog.objects.create(
            actor=changed_by,
            action=AuditLog.ACTION_ROLE_CHANGED,
            thread=thread,
            target_user=participant.user,
            metadata={'old_role': old_role, 'new_role': new_role}
        )
        
        logger.info(f"Changed role of user {user_id} in thread {thread.id} from {old_role} to {new_role}")
    
    @staticmethod
    @transaction.atomic
    def leave_thread(thread, user):
        """
        User leaves a thread
        """
        participant = ThreadParticipant.objects.get(
            thread=thread,
            user=user,
            left_at__isnull=True
        )
        
        # Owner cannot leave (must transfer ownership first)
        if participant.role == ThreadParticipant.ROLE_OWNER and thread.type == Thread.TYPE_GROUP:
            raise ValidationError("Owner must transfer ownership before leaving")
        
        participant.left_at = timezone.now()
        participant.save()
        
        logger.info(f"User {user.id} left thread {thread.id}")
    
    @staticmethod
    def get_unread_count(thread, user):
        """
        Get unread message count for user in thread
        """
        from .managers import MessageManager
        return Message.objects.count_unread_for_user(thread.id, user)


class MessageService:
    """
    Service for message-related operations
    """
    
    @staticmethod
    @transaction.atomic
    def create_message(thread, sender, content, reply_to_id=None, attachment_ids=None):
        """
        Create a new message
        """
        # Check if user can post
        if not ValidationService.can_post_in_thread(sender, thread):
            raise PermissionDenied("You don't have permission to post in this thread")
        
        # SECURITY: Sanitize content before saving to prevent XSS attacks
        if content:
            content = sanitize_message_content(content)
            # Trim whitespace after sanitization
            content = content.strip() if content else ''
        
        # Validate content not empty after sanitization
        if not content and not attachment_ids:
            raise ValidationError("Message cannot be empty")
        
        # Validate reply_to
        reply_to = None
        if reply_to_id:
            try:
                reply_to = Message.objects.get(id=reply_to_id, thread=thread)
            except Message.DoesNotExist:
                raise ValidationError("Invalid reply_to message")
        
        # Create message
        message = Message.objects.create(
            thread=thread,
            sender=sender,
            content=content,
            reply_to=reply_to,
            has_attachments=bool(attachment_ids)
        )
        
        # Link attachments
        if attachment_ids:
            Attachment.objects.filter(id__in=attachment_ids).update(message=message)
        
        # Update thread timestamp
        thread.updated_at = timezone.now()
        thread.save(update_fields=['updated_at'])
        
        # Increment unread count for all participants except sender
        participants = ThreadParticipant.objects.filter(
            thread=thread,
            left_at__isnull=True
        ).exclude(user=sender)
        
        for participant in participants:
            # Use F() expression to prevent race conditions
            from django.db.models import F
            ThreadParticipant.objects.filter(id=participant.id).update(
                unread_count=F('unread_count') + 1
            )
            # Refresh to get updated count
            participant.refresh_from_db()
            
            # Broadcast unread count update to the user's WebSocket
            MessageService._broadcast_unread_count_update(
                thread.id,
                participant.user.id,
                participant.unread_count
            )
        
        # Broadcast to WebSocket clients (Phase 2 real-time)
        MessageService._broadcast_message_new(message)
        
        logger.info(f"Created message {message.id} in thread {thread.id} by user {sender.id}")
        return message
    
    @staticmethod
    @transaction.atomic
    def update_message(message, new_content, editor):
        """
        Edit a message
        """
        if not ValidationService.can_edit_message(editor, message):
            raise PermissionDenied("You don't have permission to edit this message")
        
        if message.is_deleted():
            raise ValidationError("Cannot edit deleted message")
        
        # SECURITY: Sanitize content before saving to prevent XSS attacks
        new_content = sanitize_message_content(new_content)
        new_content = new_content.strip() if new_content else ''
        
        if not new_content:
            raise ValidationError("Message content cannot be empty")
        
        message.content = new_content
        message.edited_at = timezone.now()
        message.save()
        
        # Broadcast update to WebSocket clients (Phase 2 real-time)
        MessageService._broadcast_message_updated(message)
        
        logger.info(f"Edited message {message.id} by user {editor.id}")
        return message
    
    @staticmethod
    @transaction.atomic
    def delete_message(message, deleter):
        """
        Soft delete a message
        """
        if not ValidationService.can_edit_message(deleter, message):
            raise PermissionDenied("You don't have permission to delete this message")
        
        message.soft_delete()
        
        # Broadcast deletion to WebSocket clients (Phase 2 real-time)
        MessageService._broadcast_message_deleted(message)
        
        # Audit log
        AuditLog.objects.create(
            actor=deleter,
            action=AuditLog.ACTION_MESSAGE_DELETED,
            thread=message.thread,
            metadata={'message_id': str(message.id)}
        )
        
        logger.info(f"Deleted message {message.id} by user {deleter.id}")
    
    @staticmethod
    @transaction.atomic
    def mark_as_read(thread, user, up_to_message=None):
        """
        Mark messages as read for user
        """
        participant = ThreadParticipant.objects.get(
            thread=thread,
            user=user,
            left_at__isnull=True
        )
        
        if up_to_message:
            participant.last_read_at = up_to_message.created_at
        else:
            participant.last_read_at = timezone.now()
        
        # Reset unread count to 0
        participant.unread_count = 0
        participant.save(update_fields=['last_read_at', 'unread_count'])
        
        # Broadcast unread count update
        MessageService._broadcast_unread_count_update(
            thread.id,
            user.id,
            0
        )
        
        logger.info(f"User {user.id} marked thread {thread.id} as read")
    
    @staticmethod
    @transaction.atomic
    def add_reaction(message, user, emoji):
        """
        Add emoji reaction to message
        User can only have one reaction per message - old reaction is deleted if exists
        """
        # SECURITY: Validate emoji to prevent injection
        try:
            validate_emoji(emoji)
        except ValueError as e:
            raise ValidationError(str(e))
        
        # Check if reactions are enabled
        if message.thread.type == Thread.TYPE_GROUP:
            try:
                settings = message.thread.group_settings
                if not settings.reactions_enabled:
                    raise ValidationError("Reactions are disabled for this thread")
            except GroupSettings.DoesNotExist:
                pass
        
        # Check if user is participant
        if not ThreadParticipant.objects.filter(
            thread=message.thread,
            user=user,
            left_at__isnull=True
        ).exists():
            raise PermissionDenied("You must be a participant to react")
        
        # Delete existing reaction if any (user can only have one reaction per message)
        MessageReaction.objects.filter(
            message=message,
            user=user
        ).delete()
        
        # Create new reaction
        reaction = MessageReaction.objects.create(
            message=message,
            user=user,
            emoji=emoji
        )
        
        logger.info(f"User {user.id} reacted {emoji} to message {message.id}")
        
        # Broadcast reaction added via WebSocket
        MessageService._broadcast_reaction_added(message, user, emoji)
        
        return reaction
    
    @staticmethod
    def remove_reaction(message, user, emoji):
        """
        Remove emoji reaction from message
        """
        try:
            reaction = MessageReaction.objects.get(
                message=message,
                user=user,
                emoji=emoji
            )
            reaction.delete()
            logger.info(f"User {user.id} removed reaction {emoji} from message {message.id}")
            
            # Broadcast reaction removed via WebSocket
            MessageService._broadcast_reaction_removed(message, user, emoji)
        except MessageReaction.DoesNotExist:
            pass
    
    # WebSocket Broadcasting Methods (Phase 2 Real-Time)
    @staticmethod
    def _broadcast_message_new(message):
        """
        Broadcast new message to WebSocket clients
        """
        try:
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{message.thread_id}'
            
            # Reload message with all relationships to ensure attachments are included
            from .models import Message
            message = Message.objects.select_related(
                'sender', 'reply_to', 'thread'
            ).prefetch_related('attachments', 'reactions__user').get(id=message.id)
            
            # Serialize message
            from .serializers import MessageSerializer
            message_data = MessageSerializer(message).data
            
            # Send to all clients in thread group
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                {
                    'type': 'message_new',
                    'message': message_data,
                }
            )
            logger.debug(f"Broadcasted new message {message.id} to group {thread_group_name}")
        except Exception as e:
            logger.error(f"Error broadcasting new message: {str(e)}")
    
    @staticmethod
    def _broadcast_message_updated(message):
        """
        Broadcast message update to WebSocket clients
        """
        try:
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{message.thread_id}'
            
            # Serialize message
            from .serializers import MessageSerializer
            message_data = MessageSerializer(message).data
            
            # Send to all clients in thread group
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                {
                    'type': 'message_updated',
                    'message': message_data,
                }
            )
            logger.debug(f"Broadcasted message update {message.id} to group {thread_group_name}")
        except Exception as e:
            logger.error(f"Error broadcasting message update: {str(e)}")
    
    @staticmethod
    def _broadcast_message_deleted(message):
        """
        Broadcast message deletion to WebSocket clients
        """
        try:
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{message.thread_id}'
            
            # Send to all clients in thread group
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                {
                    'type': 'message_deleted',
                    'message_id': str(message.id),
                }
            )
            logger.debug(f"Broadcasted message deletion {message.id} to group {thread_group_name}")
        except Exception as e:
            logger.error(f"Error broadcasting message deletion: {str(e)}")
    
    @staticmethod
    def _broadcast_unread_count_update(thread_id, user_id, unread_count):
        """
        Broadcast unread count update to a specific user's WebSocket connection
        Sends to both thread-specific and global notification channels
        """
        try:
            from django.db.models import Sum
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{thread_id}'
            # Use the same group name as NotificationCountConsumer
            notifications_group_name = f'notifications_{user_id}'
            
            # Send to thread group (for users currently viewing the thread)
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                {
                    'type': 'unread_count_update',
                    'thread_id': str(thread_id),
                    'unread_count': unread_count,
                    'user_id': user_id,
                }
            )
            
            # Calculate total unread for sidebar badge
            total_unread = ThreadParticipant.objects.filter(
                user_id=user_id,
                left_at__isnull=True
            ).aggregate(
                total=Sum('unread_count')
            )['total'] or 0
            
            # Send to user's notification WebSocket channel (for cross-page updates)
            # This is the same channel used for notification.count events
            async_to_sync(channel_layer.group_send)(
                notifications_group_name,
                {
                    'type': 'chat_unread_update',
                    'thread_id': str(thread_id),
                    'unread_count': unread_count,
                    'total_unread': total_unread,
                }
            )
            
            logger.info(f"Broadcasted chat unread update for thread {thread_id} to user {user_id}: {unread_count} (total: {total_unread})")
        except Exception as e:
            logger.error(f"Error broadcasting unread count update: {str(e)}")
    
    @staticmethod
    def _broadcast_reaction_added(message, user, emoji):
        """
        Broadcast reaction added via WebSocket
        """
        try:
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{message.thread_id}'
            
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                {
                    'type': 'reaction_added',
                    'message_id': str(message.id),
                    'user_id': user.id,
                    'emoji': emoji,
                }
            )
            logger.info(f"Broadcasted reaction added: {emoji} by user {user.id} to message {message.id}")
        except Exception as e:
            logger.error(f"Error broadcasting reaction added: {str(e)}")
    
    @staticmethod
    def _broadcast_reaction_removed(message, user, emoji):
        """
        Broadcast reaction removed via WebSocket
        """
        try:
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{message.thread_id}'
            
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                {
                    'type': 'reaction_removed',
                    'message_id': str(message.id),
                    'user_id': user.id,
                    'emoji': emoji,
                }
            )
            logger.info(f"Broadcasted reaction removed: {emoji} by user {user.id} from message {message.id}")
        except Exception as e:
            logger.error(f"Error broadcasting reaction removed: {str(e)}")



class ValidationService:
    """
    Service for permission and validation checks
    """
    
    @staticmethod
    def can_post_in_thread(user, thread):
        """
        Check if user can post messages in thread
        Returns False if user is not participant or if posting is restricted to admins only
        """
        try:
            participant = ThreadParticipant.objects.get(
                thread=thread,
                user=user,
                left_at__isnull=True
            )
        except ThreadParticipant.DoesNotExist:
            return False
        
        # Direct threads: always allowed
        if thread.type == Thread.TYPE_DIRECT:
            return True
        
        # Group threads: check posting mode
        try:
            settings = thread.group_settings
            if settings.posting_mode == GroupSettings.POSTING_MODE_ADMINS_ONLY:
                return participant.role in [ThreadParticipant.ROLE_OWNER, ThreadParticipant.ROLE_ADMIN]
            return True
        except GroupSettings.DoesNotExist:
            return True
    
    @staticmethod
    def can_manage_members(user, thread):
        """
        Check if user can add/remove members (admins/owners only)
        Used for removing members and changing roles
        """
        try:
            participant = ThreadParticipant.objects.get(
                thread=thread,
                user=user,
                left_at__isnull=True
            )
            return participant.role in [ThreadParticipant.ROLE_OWNER, ThreadParticipant.ROLE_ADMIN]
        except ThreadParticipant.DoesNotExist:
            return False
    
    @staticmethod
    def can_add_members(user, thread):
        """
        Check if user can add new members to the thread
        Depends on members_can_add_others group setting
        """
        try:
            participant = ThreadParticipant.objects.get(
                thread=thread,
                user=user,
                left_at__isnull=True
            )
        except ThreadParticipant.DoesNotExist:
            return False
        
        # Admins and owners can always add members
        if participant.role in [ThreadParticipant.ROLE_OWNER, ThreadParticipant.ROLE_ADMIN]:
            return True
        
        # For regular members, check the members_can_add_others setting
        if thread.type == Thread.TYPE_GROUP:
            try:
                settings = thread.group_settings
                return settings.members_can_add_others
            except GroupSettings.DoesNotExist:
                return False
        
        return False
    
    @staticmethod
    def can_edit_message(user, message):
        """
        Check if user can edit/delete a message
        """
        # Sender can edit their own messages
        if message.sender == user:
            return True
        
        # Admins and owners can edit any message
        try:
            participant = ThreadParticipant.objects.get(
                thread=message.thread,
                user=user,
                left_at__isnull=True
            )
            return participant.role in [ThreadParticipant.ROLE_OWNER, ThreadParticipant.ROLE_ADMIN]
        except ThreadParticipant.DoesNotExist:
            return False
    
    @staticmethod
    def can_change_settings(user, thread):
        """
        Check if user can change thread settings
        """
        try:
            participant = ThreadParticipant.objects.get(
                thread=thread,
                user=user,
                left_at__isnull=True
            )
            return participant.role in [ThreadParticipant.ROLE_OWNER, ThreadParticipant.ROLE_ADMIN]
        except ThreadParticipant.DoesNotExist:
            return False


class GroupSettingsService:
    """
    Service for group settings operations
    """
    
    @staticmethod
    def broadcast_settings_updated(thread, settings, updated_by):
        """
        Broadcast group settings update to all participants via WebSocket
        
        Args:
            thread: Thread instance
            settings: GroupSettings instance
            updated_by: User who updated the settings
        """
        try:
            channel_layer = get_channel_layer()
            thread_group_name = f'thread_{thread.id}'
            
            # Prepare payload
            payload = {
                'type': 'group_settings_updated',
                'thread_id': str(thread.id),
                'settings': {
                    'posting_mode': settings.posting_mode,
                    'members_can_add_others': settings.members_can_add_others,
                },
                'updated_by': {
                    'id': updated_by.id,
                    'first_name': updated_by.first_name,
                    'last_name': updated_by.last_name
                },
                'timestamp': timezone.now().isoformat()
            }
            
            # Send to all clients in thread group
            async_to_sync(channel_layer.group_send)(
                thread_group_name,
                payload
            )
            
            logger.info(f"Broadcasted group settings update for thread {thread.id} by user {updated_by.id}")
        except Exception as e:
            logger.error(f"Error broadcasting group settings update: {str(e)}")
