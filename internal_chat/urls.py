"""
URL Configuration for Internal Chat
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'internal_chat'

router = DefaultRouter()
router.register(r'threads', views.ThreadViewSet, basename='thread')
router.register(r'attachments', views.AttachmentViewSet, basename='attachment')
router.register(r'users', views.UserListView, basename='user')

# Nested routes for messages within threads
urlpatterns = [
    path('', include(router.urls)),
    
    # Total unread count endpoint
    path(
        'unread-count/',
        views.get_total_unread_count,
        name='total-unread-count'
    ),
    
    # Messages endpoints
    path(
        'threads/<uuid:thread_id>/messages/',
        views.MessageViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='thread-messages'
    ),
    path(
        'messages/<uuid:pk>/',
        views.MessageViewSet.as_view({
            'get': 'retrieve',
            'patch': 'partial_update',
            'delete': 'destroy'
        }),
        name='message-detail'
    ),
    path(
        'messages/<uuid:pk>/read/',
        views.MessageViewSet.as_view({'post': 'read'}),
        name='message-read'
    ),
    path(
        'messages/<uuid:pk>/react/',
        views.MessageViewSet.as_view({'post': 'add_reaction'}),
        name='message-react'
    ),
    path(
        'messages/<uuid:pk>/react/<str:emoji>/',
        views.MessageViewSet.as_view({'delete': 'remove_reaction'}),
        name='message-reaction-remove'
    ),
]
