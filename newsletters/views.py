"""
Views for the newsletters system.

Implements three separate ViewSets for each news type (Normal, Slider, Achievement)
with independent pagination and image management.
"""

import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes as permission_classes_decorator
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from .models import Newsletter, NewsletterImage
from .serializers import (
    NewsletterSerializer,
    NewsletterCreateSerializer,
    NewsletterImageSerializer,
    NewsletterImageUploadSerializer
)
from .permissions import IsAdminOrReadOnly
from .pagination import NewsletterPagination
from .image_utils import process_newsletter_image

logger = logging.getLogger(__name__)


class PassthroughRenderer(BaseRenderer):
    """
    Renderer that allows binary data to pass through without modification.
    Used for image downloads.
    """
    media_type = '*/*'
    format = None
    
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class BaseNewsletterViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet for newsletters with common functionality.
    
    Subclasses override get_queryset() to filter by news_type.
    """
    
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = NewsletterPagination
    
    def get_queryset(self):
        """Override in subclasses to filter by news_type"""
        raise NotImplementedError("Subclasses must implement get_queryset()")
    
    def get_serializer_class(self):
        """Use create serializer for POST, regular serializer for GET"""
        if self.action == 'create':
            return NewsletterCreateSerializer
        return NewsletterSerializer
    
    def _handle_position_conflict(self, news_type, desired_position, exclude_id=None):
        """
        Handle position conflicts by shifting existing newsletters.
        
        When a newsletter takes a position that's already occupied:
        1. Find the next available position
        2. Move the conflicting newsletter to that position
        
        Args:
            news_type: Type of newsletter (NORMAL, SLIDER, ACHIEVEMENT)
            desired_position: The position being requested
            exclude_id: Newsletter ID to exclude (when updating existing)
        """
        # Check if position is already taken
        conflict_query = Newsletter.objects.filter(
            news_type=news_type,
            position=desired_position
        )
        
        if exclude_id:
            conflict_query = conflict_query.exclude(id=exclude_id)
        
        conflicting_newsletter = conflict_query.first()
        
        if conflicting_newsletter:
            # Find next available position
            existing_positions = set(
                Newsletter.objects.filter(news_type=news_type)
                .exclude(id=exclude_id)
                .values_list('position', flat=True)
            )
            
            # Find the lowest unused position
            next_position = 0
            while next_position in existing_positions:
                next_position += 1
            
            # Move conflicting newsletter to next available position
            conflicting_newsletter.position = next_position
            conflicting_newsletter.save()
            
            logger.info(
                f"Position conflict resolved: Moved {conflicting_newsletter.id} "
                f"from position {desired_position} to {next_position}"
            )
    
    def perform_create(self, serializer):
        """Set author to current user and auto-assign next available position"""
        news_type = serializer.validated_data.get('news_type')
        
        # Ignore any position value from frontend - calculate next available position
        existing_positions = set(
            Newsletter.objects.filter(news_type=news_type)
            .values_list('position', flat=True)
        )
        
        # Find the lowest unused position (starting from 0)
        next_position = 0
        while next_position in existing_positions:
            next_position += 1
        
        # Remove position from validated_data if present (ignore frontend value)
        serializer.validated_data.pop('position', None)
        
        # Save with auto-assigned position
        serializer.save(author=self.request.user, position=next_position)
        
        logger.info(
            f"Created newsletter with auto-assigned position {next_position} "
            f"for news_type {news_type}"
        )
    
    @action(detail=True, methods=['post'], url_path='images/upload')
    def upload_image(self, request, pk=None):
        """
        Upload image to newsletter.
        
        POST /api/newsletters/{news_type}/{id}/images/upload/
        
        Body (multipart/form-data):
        - image: Image file
        - is_main: Boolean (optional, default False)
        - display_order: Integer (optional, default 0)
        """
        newsletter = self.get_object()
        
        serializer = NewsletterImageUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Process image (validate, optimize, create thumbnail)
            image_data = process_newsletter_image(serializer.validated_data['image'])
            
            # Create NewsletterImage instance
            newsletter_image = NewsletterImage.objects.create(
                newsletter=newsletter,
                file_data=image_data['file_data'],
                thumbnail_data=image_data['thumbnail_data'],
                original_filename=image_data['original_filename'],
                file_size=image_data['file_size'],
                mime_type=image_data['mime_type'],
                is_main=serializer.validated_data.get('is_main', False),
                display_order=serializer.validated_data.get('display_order', 0)
            )
            
            result_serializer = NewsletterImageSerializer(
                newsletter_image,
                context={'request': request}
            )
            
            return Response({
                'status': 'success',
                'message': 'Image uploaded successfully',
                'data': result_serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Image upload failed: {e}")
            return Response({
                'status': 'error',
                'message': f'Image upload failed: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'], url_path='images')
    def list_images(self, request, pk=None):
        """
        List all images for newsletter.
        
        GET /api/newsletters/{news_type}/{id}/images/
        """
        newsletter = self.get_object()
        images = newsletter.images.all()
        serializer = NewsletterImageSerializer(
            images,
            many=True,
            context={'request': request}
        )
        
        return Response({
            'status': 'success',
            'data': serializer.data
        })
    
    @action(detail=False, methods=['get'], url_path='positions')
    def list_positions(self, request):
        """
        List all newsletters with ID, title, and position (display order).
        
        GET /api/newsletters/{news_type}/positions/
        
        Returns:
        {
            "status": "success",
            "data": [
                {
                    "id": 1,
                    "title": "News Title",
                    "position": 1
                },
                ...
            ]
        }
        """
        newsletters = self.get_queryset()
        
        data = [
            {
                'id': newsletter.id,
                'title': newsletter.title,
                'position': newsletter.position
            }
            for newsletter in newsletters
        ]
        
        return Response({
            'status': 'success',
            'data': data
        })
    
    @action(detail=True, methods=['patch'], url_path='update-position')
    def update_position(self, request, pk=None):
        """
        Update newsletter position with automatic conflict resolution.
        
        PATCH /api/newsletters/{news_type}/{id}/update-position/
        
        Body:
        {
            "position": 2
        }
        
        If the position is already taken, the existing newsletter at that position
        will be moved to the next available position automatically.
        
        Returns:
        {
            "status": "success",
            "message": "Position updated successfully",
            "data": {
                "id": 1,
                "title": "News Title",
                "old_position": 5,
                "new_position": 2,
                "displaced_newsletter": {
                    "id": 3,
                    "title": "Other News",
                    "old_position": 2,
                    "new_position": 6
                }
            }
        }
        """
        newsletter = self.get_object()
        new_position = request.data.get('position')
        
        if new_position is None:
            return Response({
                'status': 'error',
                'message': 'position field is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            new_position = int(new_position)
            if new_position < 0:
                raise ValueError("Position must be non-negative")
        except (ValueError, TypeError) as e:
            return Response({
                'status': 'error',
                'message': f'Invalid position value: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        old_position = newsletter.position
        
        # Check if there's a conflict before updating
        conflicting_newsletter = Newsletter.objects.filter(
            news_type=newsletter.news_type,
            position=new_position
        ).exclude(id=newsletter.id).first()
        
        displaced_info = None
        if conflicting_newsletter:
            old_conflict_position = conflicting_newsletter.position
            
            # Handle position conflict (this will move the conflicting newsletter)
            self._handle_position_conflict(
                newsletter.news_type,
                new_position,
                exclude_id=newsletter.id
            )
            
            # Refresh to get updated position
            conflicting_newsletter.refresh_from_db()
            
            displaced_info = {
                'id': conflicting_newsletter.id,
                'title': conflicting_newsletter.title,
                'old_position': old_conflict_position,
                'new_position': conflicting_newsletter.position
            }
        
        # Update the newsletter's position
        newsletter.position = new_position
        newsletter.save()
        
        response_data = {
            'id': newsletter.id,
            'title': newsletter.title,
            'old_position': old_position,
            'new_position': new_position
        }
        
        if displaced_info:
            response_data['displaced_newsletter'] = displaced_info
        
        return Response({
            'status': 'success',
            'message': 'Position updated successfully',
            'data': response_data
        })


class NormalNewsViewSet(BaseNewsletterViewSet):
    """
    ViewSet for Normal News.
    
    Endpoints:
    - GET /api/newsletters/normal/ - List (paginated)
    - POST /api/newsletters/normal/ - Create (admin only)
    - GET /api/newsletters/normal/{id}/ - Retrieve single news with all images
    - PATCH /api/newsletters/normal/{id}/ - Update (admin only)
    - DELETE /api/newsletters/normal/{id}/ - Delete (admin only)
    - POST /api/newsletters/normal/{id}/images/upload/ - Upload image
    - GET /api/newsletters/normal/{id}/images/ - List all images
    - GET /api/newsletters/normal/positions/ - List all with positions
    - PATCH /api/newsletters/normal/{id}/update-position/ - Update position
    
    The retrieve endpoint (GET /api/newsletters/normal/{id}/) returns:
    - All newsletter fields (title, details, position, author, dates)
    - All associated images with download/thumbnail URLs
    - Main image (cover image) if set
    """
    
    def get_queryset(self):
        return Newsletter.objects.with_images().by_position().filter(news_type='NORMAL')


class SliderNewsViewSet(BaseNewsletterViewSet):
    """
    ViewSet for Slider News (homepage carousel).
    
    Endpoints:
    - GET /api/newsletters/slider/ - List (paginated)
    - POST /api/newsletters/slider/ - Create (admin only)
    - GET /api/newsletters/slider/{id}/ - Retrieve single news with all images
    - PATCH /api/newsletters/slider/{id}/ - Update (admin only)
    - DELETE /api/newsletters/slider/{id}/ - Delete (admin only)
    - POST /api/newsletters/slider/{id}/images/upload/ - Upload image
    - GET /api/newsletters/slider/{id}/images/ - List all images
    - GET /api/newsletters/slider/positions/ - List all with positions
    - PATCH /api/newsletters/slider/{id}/update-position/ - Update position
    
    The retrieve endpoint (GET /api/newsletters/slider/{id}/) returns:
    - All newsletter fields (title, details, position, author, dates)
    - All associated images with download/thumbnail URLs
    - Main image (cover image) if set
    """
    
    def get_queryset(self):
        return Newsletter.objects.with_images().by_position().filter(news_type='SLIDER')


class AchievementViewSet(BaseNewsletterViewSet):
    """
    ViewSet for Employee Achievements.
    
    Endpoints:
    - GET /api/newsletters/achievement/ - List (paginated)
    - POST /api/newsletters/achievement/ - Create (admin only)
    - GET /api/newsletters/achievement/{id}/ - Retrieve single news with all images
    - PATCH /api/newsletters/achievement/{id}/ - Update (admin only)
    - DELETE /api/newsletters/achievement/{id}/ - Delete (admin only)
    - POST /api/newsletters/achievement/{id}/images/upload/ - Upload image
    - GET /api/newsletters/achievement/{id}/images/ - List all images
    - GET /api/newsletters/achievement/positions/ - List all with positions
    - PATCH /api/newsletters/achievement/{id}/update-position/ - Update position
    
    The retrieve endpoint (GET /api/newsletters/achievement/{id}/) returns:
    - All newsletter fields (title, details, position, author, dates)
    - All associated images with download/thumbnail URLs
    - Main image (cover image) if set
    """
    
    def get_queryset(self):
        return Newsletter.objects.with_images().by_position().filter(news_type='ACHIEVEMENT')


class NewsletterImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for NewsletterImage with download/thumbnail actions.
    
    Endpoints:
    - GET /api/newsletter-images/{id}/download/ - Download full image
    - GET /api/newsletter-images/{id}/thumbnail/ - Download thumbnail
    - PATCH /api/newsletter-images/{id}/ - Update is_main/display_order (admin only)
    - DELETE /api/newsletter-images/{id}/ - Delete image (admin only)
    """
    
    queryset = NewsletterImage.objects.all()
    serializer_class = NewsletterImageSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']  # Exclude POST and PUT
    
    def get_renderers(self):
        """Use PassthroughRenderer for download/thumbnail actions"""
        if self.action in ['download', 'thumbnail']:
            return [PassthroughRenderer()]
        return super().get_renderers()
    
    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """
        Download full optimized image.
        
        GET /api/newsletter-images/{id}/download/
        
        Returns: Binary image data with appropriate Content-Type
        """
        image = self.get_object()
        
        response = HttpResponse(image.file_data, content_type=image.mime_type)
        response['Content-Disposition'] = f'inline; filename="{image.original_filename}"'
        response['Content-Length'] = len(image.file_data)
        response['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response['Access-Control-Allow-Credentials'] = 'true'
        
        return response
    
    @action(detail=True, methods=['get'], url_path='thumbnail')
    def thumbnail(self, request, pk=None):
        """
        Download thumbnail image.
        
        GET /api/newsletter-images/{id}/thumbnail/
        
        Returns: Binary thumbnail data with appropriate Content-Type
        """
        image = self.get_object()
        
        if not image.thumbnail_data:
            return Response({
                'status': 'error',
                'message': 'Thumbnail not available'
            }, status=status.HTTP_404_NOT_FOUND)
        
        response = HttpResponse(image.thumbnail_data, content_type='image/jpeg')
        response['Content-Disposition'] = f'inline; filename="thumb_{image.original_filename}"'
        response['Content-Length'] = len(image.thumbnail_data)
        response['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response['Access-Control-Allow-Credentials'] = 'true'
        
        return response
    
    def update(self, request, *args, **kwargs):
        """Allow updating is_main and display_order only"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Only allow updating specific fields
        allowed_fields = {'is_main', 'display_order'}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}
        
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response({
            'status': 'success',
            'message': 'Image updated successfully',
            'data': serializer.data
        })
    
    def destroy(self, request, *args, **kwargs):
        """Delete image"""
        instance = self.get_object()
        self.perform_destroy(instance)
        
        return Response({
            'status': 'success',
            'message': 'Image deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)
