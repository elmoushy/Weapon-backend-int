"""
URL configuration for newsletters app.

Provides separate endpoints for each news type with independent pagination.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NormalNewsViewSet,
    SliderNewsViewSet,
    AchievementViewSet,
    NewsletterImageViewSet
)

# Create separate routers for each news type
normal_router = DefaultRouter()
normal_router.register(r'', NormalNewsViewSet, basename='normal-news')

slider_router = DefaultRouter()
slider_router.register(r'', SliderNewsViewSet, basename='slider-news')

achievement_router = DefaultRouter()
achievement_router.register(r'', AchievementViewSet, basename='achievement-news')

# Router for image operations
image_router = DefaultRouter()
image_router.register(r'', NewsletterImageViewSet, basename='newsletter-image')

urlpatterns = [
    # Normal news endpoints
    path('normal/', include(normal_router.urls)),
    
    # Slider news endpoints
    path('slider/', include(slider_router.urls)),
    
    # Achievement endpoints
    path('achievement/', include(achievement_router.urls)),
    
    # Image operations (shared across all news types)
    path('images/', include(image_router.urls)),
]
