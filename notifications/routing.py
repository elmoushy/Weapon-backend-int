"""
WebSocket URL routing for notifications.

This module defines the WebSocket URL patterns for the notifications system.
"""

from django.urls import re_path
from . import consumers

# WebSocket URL patterns for notification badge count
websocket_urlpatterns = [
    # Notification count WebSocket - sends unread count updates
    # Connection: ws://{host}/ws/notifications/?token={jwt_token}
    re_path(r'ws/notifications/$', consumers.NotificationCountConsumer.as_asgi()),
]
