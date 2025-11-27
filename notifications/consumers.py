"""
WebSocket Consumer for Real-Time Notifications

This module handles WebSocket connections for real-time notifications,
specifically for the notification badge count system.

The WebSocket sends ONLY the notification count - notification details 
are fetched via REST API when the user clicks the bell icon.
"""

import json
import logging
from datetime import datetime
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from asgiref.sync import sync_to_async, async_to_sync
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import jwt
from django.conf import settings
from .models import Notification, NotificationPreference

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationCountConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for notification badge count updates.
    
    Sends ONLY the unread notification count to the client.
    The actual notification list is fetched via REST API.
    
    Connection: ws://{host}/ws/notifications/?token={jwt_token}
    """
    
    async def connect(self):
        """
        Handle WebSocket connection.
        
        Authenticates the user via JWT token from query string and 
        adds them to their personal notification group.
        """
        # Extract and validate JWT token from query string
        query_string = self.scope.get('query_string', b'').decode()
        token = None
        
        for param in query_string.split('&'):
            if param.startswith('token='):
                token = param.split('=', 1)[1]
                break
        
        if not token:
            logger.warning("WebSocket connection rejected: No token provided")
            await self.close(code=4001)  # Authentication failed - Invalid token
            return
        
        # Validate JWT token and get user
        user = await self.authenticate_token(token)
        
        if user is None or isinstance(user, AnonymousUser):
            logger.warning("WebSocket connection rejected: Invalid or expired token")
            await self.close(code=4003)  # Authorization failed - Token expired
            return
        
        self.user = user
        self.room_name = f"notifications_{user.id}"
        
        # Join user's personal notification group
        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        # Send initial unread count
        count = await self.get_unread_count()
        await self.send_json({
            "type": "notification.count",
            "count": count,
            "timestamp": timezone.now().isoformat()
        })
        
        logger.info(f"WebSocket connected for notifications: {self.user.email} (count: {count})")
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        
        Removes the user from their notification group.
        """
        if hasattr(self, 'room_name'):
            await self.channel_layer.group_discard(
                self.room_name,
                self.channel_name
            )
        
        if hasattr(self, 'user') and not isinstance(self.user, AnonymousUser):
            logger.info(f"WebSocket disconnected for notifications: {self.user.email} (code: {close_code})")
    
    async def receive_json(self, content):
        """
        Handle messages received from WebSocket client.
        
        Supports ping/pong for heartbeat.
        """
        message_type = content.get('type')
        
        if message_type == 'pong':
            # Client responding to ping - no action needed
            pass
        elif message_type == 'ping':
            # Client sending ping, respond with pong
            await self.send_json({
                'type': 'pong',
                'timestamp': timezone.now().isoformat()
            })
        else:
            logger.debug(f"Unknown WebSocket message type: {message_type}")
    
    async def send_notification_count(self, event):
        """
        Handler for notification count updates sent to the group.
        
        Called when a notification is created, read, or deleted.
        """
        await self.send_json({
            "type": "notification.count",
            "count": event["count"],
            "timestamp": timezone.now().isoformat()
        })
    
    async def chat_unread_update(self, event):
        """
        Handler for chat unread count updates sent to the group.
        
        Called when a new message is created in a thread.
        Sends the thread-specific and total unread counts to the client.
        """
        await self.send_json({
            "type": "chat.unread.update",
            "thread_id": event["thread_id"],
            "unread_count": event["unread_count"],
            "total_unread": event["total_unread"]
        })
        logger.debug(f"Sent chat unread update to user {self.user.id}: thread={event['thread_id']}, count={event['unread_count']}, total={event['total_unread']}")
    
    @database_sync_to_async
    def authenticate_token(self, token):
        """
        Authenticate JWT token and return user.
        
        Args:
            token: JWT token string
            
        Returns:
            User object or None if authentication fails
        """
        try:
            # Validate JWT token
            UntypedToken(token)
            
            # Decode token to get user_id
            decoded_data = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )
            user_id = decoded_data.get('user_id')
            
            if user_id:
                return User.objects.get(id=user_id)
            return None
            
        except (InvalidToken, TokenError, jwt.DecodeError, User.DoesNotExist) as e:
            logger.warning(f"Token authentication failed: {e}")
            return None
    
    @database_sync_to_async
    def get_unread_count(self):
        """Get the number of unread notifications for the user."""
        return Notification.objects.filter(
            recipient=self.user,
            is_read=False
        ).count()


# Helper function to send notification count update from anywhere in the app
def send_notification_count_update(user_id: int):
    """
    Send updated notification count to user's WebSocket.
    
    This function can be called from signals, views, or services
    to push the latest count to the user.
    
    Args:
        user_id: ID of the user to send the count update to
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("Channel layer not configured, skipping WebSocket notification")
            return
        
        # Get the current unread count
        count = Notification.objects.filter(
            recipient_id=user_id,
            is_read=False
        ).count()
        
        # Send to user's notification group
        async_to_sync(channel_layer.group_send)(
            f"notifications_{user_id}",
            {
                "type": "send_notification_count",
                "count": count
            }
        )
        
        logger.debug(f"Sent notification count update to user {user_id}: {count}")
        
    except Exception as e:
        logger.error(f"Failed to send notification count update to user {user_id}: {e}")


# Async version of the helper function
async def async_send_notification_count_update(user_id: int):
    """
    Async version: Send updated notification count to user's WebSocket.
    
    Args:
        user_id: ID of the user to send the count update to
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("Channel layer not configured, skipping WebSocket notification")
            return
        
        # Get the current unread count
        @database_sync_to_async
        def get_count():
            return Notification.objects.filter(
                recipient_id=user_id,
                is_read=False
            ).count()
        
        count = await get_count()
        
        # Send to user's notification group
        await channel_layer.group_send(
            f"notifications_{user_id}",
            {
                "type": "send_notification_count",
                "count": count
            }
        )
        
        logger.debug(f"Sent async notification count update to user {user_id}: {count}")
        
    except Exception as e:
        logger.error(f"Failed to send async notification count update to user {user_id}: {e}")


# Legacy consumer class (kept for reference, not used)
class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for handling real-time notifications.
    
    Manages user connections, authentication, and real-time notification delivery.
    """
    
    async def connect(self):
        """
        Handle WebSocket connection.
        
        Authenticates the user and adds them to their personal notification group.
        """
        self.user = self.scope["user"]
        
        # Only allow authenticated users
        if isinstance(self.user, AnonymousUser):
            logger.warning("WebSocket connection rejected: User not authenticated")
            await self.close(code=4001)  # Unauthorized
            return
        
        # Create a personal notification channel for this user
        self.notification_group_name = f"user_notifications_{self.user.id}"
        
        # Configuration for pong responses
        self.send_pong_on_notification = True  # Can be configured per connection
        
        # Join user's personal notification group
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'user_id': self.user.id,
            'user_email': self.user.email,
            'message': 'WebSocket connection established successfully',
            'pong_on_notification': self.send_pong_on_notification
        }))
        
        logger.info(f"WebSocket connected: {self.user.email}")
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        
        Removes the user from their notification group.
        """
        if hasattr(self, 'notification_group_name'):
            await self.channel_layer.group_discard(
                self.notification_group_name,
                self.channel_name
            )
        
        if hasattr(self, 'user') and not isinstance(self.user, AnonymousUser):
            logger.info(f"WebSocket disconnected: {self.user.email} (code: {close_code})")
    
    async def receive(self, text_data):
        """
        Handle messages received from WebSocket client.
        
        Supports actions like marking notifications as read.
        """
        try:
            data = json.loads(text_data)
            action = data.get('type')
            
            if action == 'mark_read':
                await self.handle_mark_read(data)
            elif action == 'mark_all_read':
                await self.handle_mark_all_read()
            elif action == 'get_unread_count':
                await self.handle_get_unread_count()
            elif action == 'ping':
                # Respond to ping to keep connection alive
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'trigger': 'ping',
                    'timestamp': data.get('timestamp')
                }))
            elif action == 'configure_pong':
                # Configure pong behavior
                await self.handle_configure_pong(data)
            else:
                logger.warning(f"Unknown WebSocket action: {action}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown action: {action}'
                }))
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received via WebSocket")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))
    
    async def handle_mark_read(self, data):
        """Handle marking a specific notification as read."""
        notification_id = data.get('notification_id')
        if not notification_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'notification_id is required'
            }))
            return
        
        try:
            success = await self.mark_notification_read(notification_id)
            if success:
                await self.send(text_data=json.dumps({
                    'type': 'notification_marked_read',
                    'notification_id': notification_id
                }))
                # Send updated unread count
                await self.handle_get_unread_count()
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Notification not found or already read'
                }))
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to mark notification as read'
            }))
    
    async def handle_mark_all_read(self):
        """Handle marking all notifications as read for the user."""
        try:
            count = await self.mark_all_notifications_read()
            await self.send(text_data=json.dumps({
                'type': 'all_notifications_marked_read',
                'count': count
            }))
            # Send updated unread count
            await self.handle_get_unread_count()
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to mark all notifications as read'
            }))
    
    async def handle_get_unread_count(self):
        """Handle getting unread notification count."""
        try:
            count = await self.get_unread_count()
            await self.send(text_data=json.dumps({
                'type': 'unread_count',
                'count': count
            }))
        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
    
    async def handle_configure_pong(self, data):
        """Handle configuring pong response behavior."""
        try:
            # Configure whether to send pong on new notifications
            send_pong = data.get('send_pong_on_notification', True)
            self.send_pong_on_notification = bool(send_pong)
            
            await self.send(text_data=json.dumps({
                'type': 'pong_configuration_updated',
                'send_pong_on_notification': self.send_pong_on_notification
            }))
            
            logger.info(f"Updated pong configuration for user {self.user.email}: {self.send_pong_on_notification}")
            
        except Exception as e:
            logger.error(f"Error configuring pong behavior: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to configure pong behavior'
            }))
    
    # Group message handlers
    async def notification_message(self, event):
        """
        Handle notification messages sent to the group.
        
        Called when a notification is sent to this user's group.
        Sends the notification and optionally a pong response based on configuration.
        """
        try:
            # Get user's preferred language
            lang = await self.get_user_preferred_language()
            
            # Send notification to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'new_notification',
                'notification': event['notification'],
                'lang': lang
            }))
            
            # Send pong response only if configured to do so
            if getattr(self, 'send_pong_on_notification', True):
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'trigger': 'new_notification',
                    'notification_id': event['notification'].get('id'),
                    'timestamp': event['notification'].get('created_at')
                }))
                
                logger.debug(f"Sent new notification with pong response for user {self.user.email}")
            else:
                logger.debug(f"Sent new notification without pong response for user {self.user.email}")
            
        except Exception as e:
            logger.error(f"Error sending notification message: {e}")
    
    # Database operations (async)
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark a specific notification as read."""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user,
                is_read=False
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False
    
    @database_sync_to_async
    def mark_all_notifications_read(self):
        """Mark all unread notifications as read for the user."""
        from django.utils import timezone
        
        unread_notifications = Notification.objects.filter(
            recipient=self.user,
            is_read=False
        )
        count = unread_notifications.count()
        
        unread_notifications.update(
            is_read=True,
            read_at=timezone.now()
        )
        
        return count
    
    @database_sync_to_async
    def get_unread_count(self):
        """Get the number of unread notifications for the user."""
        return Notification.objects.filter(
            recipient=self.user,
            is_read=False
        ).count()
    
    @database_sync_to_async
    def get_user_preferred_language(self):
        """Get user's preferred language for notifications."""
        try:
            preferences = NotificationPreference.objects.get(user=self.user)
            return preferences.preferred_language
        except NotificationPreference.DoesNotExist:
            return 'en'  # Default to English
