"""
Custom Model Managers for optimized queries
"""
from django.db import models
from django.db.models import Q, Count, Max, Prefetch
from django.utils import timezone


class ThreadManager(models.Manager):
    """
    Optimized query manager for Thread model
    """
    
    def for_user(self, user):
        """
        Get all threads where user is an active participant
        """
        return self.filter(
            participants__user=user,
            participants__left_at__isnull=True
        ).distinct()
    
    def with_last_message(self):
        """
        Prefetch last message for each thread
        """
        from .models import Message
        return self.prefetch_related(
            Prefetch(
                'messages',
                queryset=Message.objects.filter(deleted_at__isnull=True).order_by('-created_at')[:1],
                to_attr='last_message_list'
            )
        )
    
    def with_participant_info(self):
        """
        Prefetch participants with user details
        """
        return self.prefetch_related(
            Prefetch(
                'participants',
                queryset=models.QuerySet(model=self.model.participants.rel.model).filter(
                    left_at__isnull=True
                ).select_related('user')
            )
        )
    
    def active(self):
        """
        Get non-archived threads
        """
        return self.filter(is_archived=False)
    
    def direct_threads(self):
        """
        Get only direct threads
        """
        return self.filter(type='direct')
    
    def group_threads(self):
        """
        Get only group threads
        """
        return self.filter(type='group')


class MessageManager(models.Manager):
    """
    Optimized query manager for Message model
    """
    
    def active(self):
        """
        Get non-deleted messages
        """
        return self.filter(deleted_at__isnull=True)
    
    def for_thread(self, thread_id):
        """
        Get all active messages for a thread with sender info
        """
        return self.filter(
            thread_id=thread_id,
            deleted_at__isnull=True
        ).select_related('sender').prefetch_related('attachments', 'reactions')
    
    def with_attachments(self):
        """
        Prefetch attachments
        """
        return self.prefetch_related('attachments')
    
    def with_reactions(self):
        """
        Prefetch reactions with user info
        """
        return self.prefetch_related(
            Prefetch(
                'reactions',
                queryset=models.QuerySet(model=self.model.reactions.rel.model).select_related('user')
            )
        )
    
    def unread_for_user(self, thread_id, user):
        """
        Get unread messages for a user in a thread
        """
        from .models import ThreadParticipant
        
        try:
            participant = ThreadParticipant.objects.get(thread_id=thread_id, user=user)
            last_read_at = participant.last_read_at
            
            if last_read_at:
                return self.filter(
                    thread_id=thread_id,
                    created_at__gt=last_read_at,
                    deleted_at__isnull=True
                ).exclude(sender=user)
            else:
                # Never read any messages
                return self.filter(
                    thread_id=thread_id,
                    deleted_at__isnull=True
                ).exclude(sender=user)
        except ThreadParticipant.DoesNotExist:
            return self.none()
    
    def count_unread_for_user(self, thread_id, user):
        """
        Count unread messages for a user in a thread
        """
        return self.unread_for_user(thread_id, user).count()


class ThreadParticipantManager(models.Manager):
    """
    Optimized query manager for ThreadParticipant model
    """
    
    def active(self):
        """
        Get active participants (not left)
        """
        return self.filter(left_at__isnull=True)
    
    def for_user(self, user):
        """
        Get all participations for a user
        """
        return self.filter(user=user, left_at__isnull=True).select_related('thread')
    
    def owners(self):
        """
        Get only owners
        """
        return self.filter(role='owner', left_at__isnull=True)
    
    def admins(self):
        """
        Get owners and admins
        """
        return self.filter(
            Q(role='owner') | Q(role='admin'),
            left_at__isnull=True
        )
    
    def members(self):
        """
        Get only members (not admins or owners)
        """
        return self.filter(role='member', left_at__isnull=True)
    
    def is_participant(self, thread_id, user):
        """
        Check if user is an active participant in thread
        """
        return self.filter(
            thread_id=thread_id,
            user=user,
            left_at__isnull=True
        ).exists()
    
    def get_role(self, thread_id, user):
        """
        Get user's role in a thread
        Returns None if not a participant
        """
        try:
            participant = self.get(
                thread_id=thread_id,
                user=user,
                left_at__isnull=True
            )
            return participant.role
        except self.model.DoesNotExist:
            return None
    
    def is_owner_or_admin(self, thread_id, user):
        """
        Check if user is owner or admin in thread
        """
        return self.filter(
            thread_id=thread_id,
            user=user,
            role__in=['owner', 'admin'],
            left_at__isnull=True
        ).exists()


class AttachmentManager(models.Manager):
    """
    Optimized query manager for Attachment model
    """
    
    def for_message(self, message_id):
        """
        Get all attachments for a message
        """
        return self.filter(message_id=message_id)
    
    def by_content_type(self, content_type):
        """
        Filter by content type (e.g., 'image/jpeg')
        """
        return self.filter(content_type=content_type)
    
    def images(self):
        """
        Get only image attachments
        """
        return self.filter(content_type__startswith='image/')
    
    def documents(self):
        """
        Get only document attachments
        """
        return self.filter(
            Q(content_type='application/pdf') |
            Q(content_type__contains='word') |
            Q(content_type__contains='excel') |
            Q(content_type__contains='sheet')
        )
