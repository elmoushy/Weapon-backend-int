"""
Views for the quicklinks system.

Implements ViewSet for Quick Links with:
- CRUD operations
- Icon upload/download/delete
- Bulk position updates
- Admin-only write access
"""

import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import QuickLink
from .serializers import (
    QuickLinkSerializer,
    QuickLinkCreateSerializer,
    QuickLinkUpdateSerializer,
    QuickLinkIconUploadSerializer,
    BulkPositionUpdateSerializer,
)
from .permissions import IsAdminOrReadOnly
from .pagination import QuickLinkPagination
from .image_utils import process_quicklink_icon

logger = logging.getLogger(__name__)


def download_icon(request, pk):
    """
    Download icon for a quick link.
    
    This is a plain Django view that bypasses DRF content negotiation
    to properly serve binary image data.
    
    Authentication is handled manually via JWT token validation.
    """
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework.exceptions import AuthenticationFailed
    
    # Manual JWT authentication
    jwt_auth = JWTAuthentication()
    try:
        auth_result = jwt_auth.authenticate(request)
        if auth_result is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Authentication credentials were not provided.',
                'data': None
            }, status=401)
        user, token = auth_result
    except AuthenticationFailed as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'data': None
        }, status=401)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': 'Authentication failed.',
            'data': None
        }, status=401)
    
    # Get the quicklink
    quicklink = get_object_or_404(QuickLink, pk=pk)
    
    if not quicklink.has_icon:
        return JsonResponse({
            'status': 'error',
            'message': 'Quick link does not have an icon',
            'data': None
        }, status=404)
    
    # Return icon as binary response
    response = HttpResponse(
        quicklink.icon_data,
        content_type=quicklink.icon_mime_type or 'application/octet-stream'
    )
    
    # Set content disposition for inline display
    filename = quicklink.icon_original_filename or f'icon-{quicklink.pk}'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Content-Length'] = len(quicklink.icon_data)
    
    # Cache headers
    response['Cache-Control'] = 'public, max-age=86400'  # 24 hours
    
    return response


class PassthroughRenderer(BaseRenderer):
    """
    Renderer that allows binary data to pass through without modification.
    Used for icon downloads.
    """
    media_type = '*/*'
    format = None
    
    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class QuickLinkViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Quick Links CRUD operations.
    
    Endpoints:
    - GET /quicklinks/ - List quick links (paginated)
    - GET /quicklinks/{id}/ - Get single quick link
    - POST /quicklinks/ - Create quick link (admin only)
    - PATCH /quicklinks/{id}/ - Update quick link (admin only)
    - DELETE /quicklinks/{id}/ - Delete quick link (admin only)
    - POST /quicklinks/{id}/icon/ - Upload icon (admin only)
    - DELETE /quicklinks/{id}/icon/ - Delete icon (admin only)
    - GET /quicklinks/{id}/icon/ - Download icon
    - PATCH /quicklinks/positions/ - Bulk update positions (admin only)
    """
    
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    pagination_class = QuickLinkPagination
    
    def get_queryset(self):
        """
        Return quick links ordered by position.
        
        Admin users see all links, regular users see only active links.
        """
        user = self.request.user
        user_role = getattr(user, 'role', None)
        
        # Defer icon_data to avoid loading BLOBs in list views
        base_queryset = QuickLink.objects.defer('icon_data').by_position()
        
        # Admin users see all, regular users see only active
        if user_role in ['admin', 'super_admin']:
            queryset = base_queryset
        else:
            queryset = base_queryset.active()
        
        # Optional filter by is_active query param
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_active=is_active_bool)
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return QuickLinkCreateSerializer
        elif self.action in ('update', 'partial_update'):
            return QuickLinkUpdateSerializer
        return QuickLinkSerializer
    
    def list(self, request, *args, **kwargs):
        """List quick links with custom response format"""
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'status': 'success',
            'message': 'Quick links retrieved successfully',
            'data': {
                'count': len(serializer.data),
                'results': serializer.data
            }
        })
    
    def retrieve(self, request, *args, **kwargs):
        """Get single quick link with custom response format"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'status': 'success',
            'message': 'Quick link retrieved successfully',
            'data': serializer.data
        })
    
    def create(self, request, *args, **kwargs):
        """Create a new quick link"""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': 'Validation error',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Auto-assign position if not provided
        position = serializer.validated_data.get('position')
        if position is None:
            # Get next available position
            existing_positions = set(
                QuickLink.objects.values_list('position', flat=True)
            )
            next_position = 0
            while next_position in existing_positions:
                next_position += 1
            serializer.validated_data['position'] = next_position
        
        # Set creator
        quicklink = serializer.save(created_by=request.user)
        
        # Return created object with full serializer
        response_serializer = QuickLinkSerializer(quicklink, context={'request': request})
        
        return Response({
            'status': 'success',
            'message': 'Quick link created successfully',
            'data': response_serializer.data
        }, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        """Full update of quick link"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': 'Validation error',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        self.perform_update(serializer)
        
        # Return updated object
        response_serializer = QuickLinkSerializer(instance, context={'request': request})
        
        return Response({
            'status': 'success',
            'message': 'Quick link updated successfully',
            'data': response_serializer.data
        })
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update of quick link"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete quick link"""
        instance = self.get_object()
        instance.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['get'], url_path='icon', renderer_classes=[PassthroughRenderer])
    def icon(self, request, pk=None):
        """
        Download icon for quick link.
        
        GET: Download icon as binary
        """
        quicklink = self.get_object()
        return self._download_icon_response(request, quicklink)
    
    @icon.mapping.post
    def icon_upload(self, request, pk=None):
        """Upload icon to quick link"""
        quicklink = self.get_object()
        return self._upload_icon(request, quicklink)
    
    @icon.mapping.delete
    def icon_delete(self, request, pk=None):
        """Delete icon from quick link"""
        quicklink = self.get_object()
        return self._delete_icon(request, quicklink)
    
    def _download_icon_response(self, request, quicklink):
        """Download icon for quick link - returns binary response"""
        if not quicklink.has_icon:
            return Response({
                'status': 'error',
                'message': 'Quick link does not have an icon',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Return icon as binary response
        response = HttpResponse(
            quicklink.icon_data,
            content_type=quicklink.icon_mime_type or 'application/octet-stream'
        )
        
        # Set content disposition for inline display
        filename = quicklink.icon_original_filename or f'icon-{quicklink.pk}'
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = len(quicklink.icon_data)
        response['Cache-Control'] = 'public, max-age=86400'  # 24 hours
        
        return response
    
    @action(detail=True, methods=['get'], url_path='icon/download', renderer_classes=[PassthroughRenderer])
    def icon_download(self, request, pk=None):
        """
        Download icon for quick link.
        
        GET: Download icon as binary
        """
        quicklink = self.get_object()
        return self._download_icon(request, quicklink)
    
    def _upload_icon(self, request, quicklink):
        """Upload icon to quick link"""
        serializer = QuickLinkIconUploadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': 'Invalid file',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Process icon (validate, optimize)
            icon_data = process_quicklink_icon(serializer.validated_data['icon'])
            
            # Update quick link with new icon
            quicklink.icon_data = icon_data['icon_data']
            quicklink.icon_mime_type = icon_data['mime_type']
            quicklink.icon_original_filename = icon_data['original_filename']
            quicklink.save()
            
            # Generate icon URL
            icon_url = request.build_absolute_uri(
                f'/api/quicklinks/{quicklink.pk}/icon/'
            )
            
            return Response({
                'status': 'success',
                'message': 'Icon uploaded successfully',
                'data': {
                    'icon_url': icon_url
                }
            })
            
        except Exception as e:
            logger.error(f"Icon upload failed: {e}")
            return Response({
                'status': 'error',
                'message': f'Icon upload failed: {str(e)}',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _delete_icon(self, request, quicklink):
        """Remove icon from quick link"""
        if not quicklink.has_icon:
            return Response({
                'status': 'error',
                'message': 'Quick link does not have an icon',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        
        quicklink.clear_icon()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def _download_icon(self, request, quicklink):
        """Download icon for quick link"""
        if not quicklink.has_icon:
            return Response({
                'status': 'error',
                'message': 'Quick link does not have an icon',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Return icon as binary response
        response = HttpResponse(
            quicklink.icon_data,
            content_type=quicklink.icon_mime_type or 'application/octet-stream'
        )
        
        # Set content disposition for download
        filename = quicklink.icon_original_filename or f'icon-{quicklink.pk}'
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = len(quicklink.icon_data)
        
        # Cache headers
        response['Cache-Control'] = 'public, max-age=86400'  # 24 hours
        
        return response
    
    @action(detail=False, methods=['patch'], url_path='positions')
    def positions(self, request):
        """
        Bulk update positions of multiple quick links.
        
        PATCH /quicklinks/positions/
        
        Body:
        {
            "positions": [
                {"id": 1, "position": 0},
                {"id": 2, "position": 1},
                {"id": 3, "position": 2}
            ]
        }
        """
        serializer = BulkPositionUpdateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': 'Validation error',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        positions_data = serializer.validated_data['positions']
        
        # Verify all IDs exist
        ids = [item['id'] for item in positions_data]
        existing_ids = set(
            QuickLink.objects.filter(id__in=ids).values_list('id', flat=True)
        )
        
        missing_ids = set(ids) - existing_ids
        if missing_ids:
            return Response({
                'status': 'error',
                'message': f'Quick links not found: {list(missing_ids)}',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Update positions in a transaction
        with transaction.atomic():
            for item in positions_data:
                QuickLink.objects.filter(id=item['id']).update(position=item['position'])
        
        logger.info(f"Updated positions for {len(positions_data)} quick links")
        
        return Response({
            'status': 'success',
            'message': 'Positions updated successfully',
            'data': None
        })
