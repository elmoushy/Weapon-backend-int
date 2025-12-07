"""
URL configuration for quicklinks app.

Provides endpoints for Quick Links CRUD and icon management.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuickLinkViewSet, download_icon

# Create router for QuickLink viewset
router = DefaultRouter()
router.register(r'', QuickLinkViewSet, basename='quicklink')

urlpatterns = [
    # Direct icon download endpoint (bypasses DRF content negotiation) - GET only
    path('<int:pk>/icon/download/', download_icon, name='quicklink-icon-download'),
    # Router URLs (includes POST/DELETE to /icon/ via viewset actions)
    path('', include(router.urls)),
]
