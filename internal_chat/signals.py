"""
Django Signals for Internal Chat
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message, ThreadParticipant, AuditLog

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Message)
def notify_new_message(sender, instance, created, **kwargs):
    """
    Send notification when new message is created
    """
    if not created or instance.is_deleted():
        return
    
    try:
        from notifications.services import NotificationService
        
        # Get all participants except sender
        participants = ThreadParticipant.objects.filter(
            thread=instance.thread,
            left_at__isnull=True
        ).exclude(user=instance.sender).select_related('user')
        
        for participant in participants:
            # Skip if muted
            if participant.is_muted:
                continue
            
            # Create notification
            thread_title = instance.thread.title or f"Direct chat"
            NotificationService.create_notification(
                recipient=participant.user,
                notification_type='chat_message',
                title=f'New message in {thread_title}',
                body=instance.content[:100],
                action_url=f'/chat/{instance.thread.id}',
                sender=instance.sender,
                metadata={
                    'thread_id': str(instance.thread.id),
                    'message_id': str(instance.id),
                    'sender_id': instance.sender.id if instance.sender else None
                }
            )
        
        logger.info(f"Sent notifications for message {instance.id} to {participants.count()} participants")
    
    except ImportError:
        logger.warning("NotificationService not available, skipping notifications")
    except Exception as e:
        logger.error(f"Error sending message notifications: {str(e)}")


@receiver(post_save, sender=ThreadParticipant)
def notify_member_added(sender, instance, created, **kwargs):
    """
    Notify user when added to a thread
    """
    if not created:
        return
    
    try:
        from notifications.services import NotificationService
        
        thread_title = instance.thread.title or "a direct chat"
        NotificationService.create_notification(
            recipient=instance.user,
            notification_type='chat_member_added',
            title=f'Added to {thread_title}',
            body=f'You have been added to {thread_title}',
            action_url=f'/chat/{instance.thread.id}',
            metadata={
                'thread_id': str(instance.thread.id),
                'role': instance.role
            }
        )
        
        logger.info(f"Sent member added notification to user {instance.user.id}")
    
    except ImportError:
        logger.warning("NotificationService not available, skipping notifications")
    except Exception as e:
        logger.error(f"Error sending member added notification: {str(e)}")


@receiver(post_save, sender=AuditLog)
def notify_audit_actions(sender, instance, created, **kwargs):
    """
    Notify users about significant audit events
    """
    if not created:
        return
    
    try:
        from notifications.services import NotificationService
        
        # Notify target user for role changes or removal
        if instance.target_user and instance.action in [
            AuditLog.ACTION_ROLE_CHANGED,
            AuditLog.ACTION_MEMBER_REMOVED
        ]:
            if instance.action == AuditLog.ACTION_ROLE_CHANGED:
                new_role = instance.metadata.get('new_role', 'member')
                thread_title = instance.thread.title if instance.thread else "a chat"
                NotificationService.create_notification(
                    recipient=instance.target_user,
                    notification_type='chat_role_changed',
                    title='Role changed',
                    body=f'Your role in {thread_title} has been changed to {new_role}',
                    action_url=f'/chat/{instance.thread.id}' if instance.thread else None,
                    metadata={
                        'thread_id': str(instance.thread.id) if instance.thread else None,
                        'new_role': new_role
                    }
                )
            
            elif instance.action == AuditLog.ACTION_MEMBER_REMOVED:
                thread_title = instance.thread.title if instance.thread else "a chat"
                NotificationService.create_notification(
                    recipient=instance.target_user,
                    notification_type='chat_member_removed',
                    title='Removed from chat',
                    body=f'You have been removed from {thread_title}',
                    metadata={
                        'thread_id': str(instance.thread.id) if instance.thread else None
                    }
                )
    
    except ImportError:
        logger.warning("NotificationService not available, skipping notifications")
    except Exception as e:
        logger.error(f"Error sending audit action notifications: {str(e)}")
