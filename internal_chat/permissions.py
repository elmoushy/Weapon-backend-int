"""
Custom DRF Permissions for Internal Chat
"""
from rest_framework import permissions
from .models import ThreadParticipant, Message
from .services import ValidationService


class IsThreadParticipant(permissions.BasePermission):
    """
    Permission check: user must be an active participant in the thread
    """
    message = "You must be a participant to access this thread"
    
    def has_object_permission(self, request, view, obj):
        # obj can be Thread, Message, or other thread-related object
        if hasattr(obj, 'thread'):
            thread = obj.thread
        else:
            thread = obj
        
        return ThreadParticipant.objects.filter(
            thread=thread,
            user=request.user,
            left_at__isnull=True
        ).exists()


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission check: user must be owner or admin of the thread
    """
    message = "You must be an owner or admin to perform this action"
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'thread'):
            thread = obj.thread
        else:
            thread = obj
        
        return ValidationService.can_manage_members(request.user, thread)


class CanPostInThread(permissions.BasePermission):
    """
    Permission check: user can post messages in the thread
    Respects posting_mode group setting
    """
    message = "Only admins can post in this group"
    
    def has_permission(self, request, view):
        # For create operations, check thread_id from URL or request data
        if request.method == 'POST':
            thread_id = view.kwargs.get('thread_id') or request.data.get('thread')
            if not thread_id:
                return False
            
            from .models import Thread
            try:
                thread = Thread.objects.get(id=thread_id)
                return ValidationService.can_post_in_thread(request.user, thread)
            except Thread.DoesNotExist:
                return False
        
        return True
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'thread'):
            thread = obj.thread
        else:
            thread = obj
        
        return ValidationService.can_post_in_thread(request.user, thread)


class CanAddMembers(permissions.BasePermission):
    """
    Permission check: user can add members to the thread
    Respects members_can_add_others group setting
    """
    message = "Only admins can add members to this group"
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'thread'):
            thread = obj.thread
        else:
            thread = obj
        
        return ValidationService.can_add_members(request.user, thread)


class IsMessageSenderOrAdmin(permissions.BasePermission):
    """
    Permission check: user must be message sender or thread admin
    """
    message = "You don't have permission to modify this message"
    
    def has_object_permission(self, request, view, obj):
        # obj is a Message
        return ValidationService.can_edit_message(request.user, obj)


class CanChangeSettings(permissions.BasePermission):
    """
    Permission check: user can change thread settings
    """
    message = "You don't have permission to change thread settings"
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'thread'):
            thread = obj.thread
        else:
            thread = obj
        
        return ValidationService.can_change_settings(request.user, thread)
