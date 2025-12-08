"""
Views for the quicklinks system.

Implements ViewSet for Quick Links with:
- CRUD operations
- Icon upload/download/delete
- Bulk position updates
- Admin-only write access
- User-specific ordering (pinned, recent, others)
- Pin/unpin toggle endpoint
- Click tracking endpoint
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

from .models import QuickLink, UserQuickLinkPreference
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
    - POST /quicklinks/{id}/pin/ - Toggle pin status for current user
    - POST /quicklinks/{id}/click/ - Record a click for current user
    - GET /quicklinks/my-preferences/ - Get user's pinned and recent links
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
    
    def get_serializer_context(self):
        """Add user preferences to serializer context"""
        context = super().get_serializer_context()
        
        # Add user preferences for personalized data
        if self.request.user.is_authenticated:
            user_prefs = {
                pref.quicklink_id: pref 
                for pref in UserQuickLinkPreference.objects.filter(user=self.request.user)
            }
            context['user_prefs'] = user_prefs
        
        return context
    
    def list(self, request, *args, **kwargs):
        """
        List quick links with custom response format.
        
        Returns links ordered by user preference:
        1. Pinned first (by pin_order)
        2. Recently accessed
        3. Remaining by default position
        """
        user = request.user
        base_queryset = self.get_queryset()
        
        # Get ordered quicklinks for this user
        quicklinks, user_prefs = UserQuickLinkPreference.get_ordered_quicklinks_for_user(
            user, 
            base_queryset
        )
        
        # Use pagination if configured
        page_size = request.query_params.get('page_size', 20)
        page = request.query_params.get('page', 1)
        
        try:
            page_size = int(page_size)
            page = int(page)
        except ValueError:
            page_size = 20
            page = 1
        
        # Calculate pagination
        total_count = len(quicklinks)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_quicklinks = quicklinks[start_idx:end_idx]
        
        # Serialize with user preferences context
        serializer = self.get_serializer(
            paginated_quicklinks, 
            many=True, 
            context={
                'request': request,
                'user_prefs': user_prefs
            }
        )
        
        return Response({
            'status': 'success',
            'message': 'Quick links retrieved successfully',
            'data': {
                'count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size,
                'current_page': page,
                'page_size': page_size,
                'next': None if end_idx >= total_count else f'?page={page + 1}&page_size={page_size}',
                'previous': None if page <= 1 else f'?page={page - 1}&page_size={page_size}',
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
            
            # Generate icon URL (ensure HTTPS in production)
            from weaponpowercloud_backend.utils import build_absolute_uri_https
            icon_url = build_absolute_uri_https(
                request,
                f'/api/quicklinks/{quicklink.pk}/icon/',
                use_reverse=False
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
    
    @action(detail=True, methods=['post'], url_path='pin')
    def pin(self, request, pk=None):
        """
        Toggle pin status for a quick link for the current user.
        
        POST /quicklinks/{id}/pin/
        
        Returns:
            is_pinned: boolean - new pin status
        """
        quicklink = self.get_object()
        user = request.user
        
        pref, is_now_pinned = UserQuickLinkPreference.toggle_pin(user, quicklink)
        
        logger.info(f"User {user.id} {'pinned' if is_now_pinned else 'unpinned'} quicklink {quicklink.id}")
        
        return Response({
            'status': 'success',
            'message': 'تم التثبيت بنجاح' if is_now_pinned else 'تم إلغاء التثبيت',
            'data': {
                'quicklink_id': quicklink.id,
                'is_pinned': is_now_pinned,
                'pin_order': pref.pin_order if is_now_pinned else None
            }
        })
    
    @action(detail=True, methods=['post'], url_path='click')
    def click(self, request, pk=None):
        """
        Record a click/access for a quick link by the current user.
        
        POST /quicklinks/{id}/click/
        
        This updates the last_accessed_at timestamp and click_count
        for personalized ordering.
        """
        quicklink = self.get_object()
        user = request.user
        
        pref = UserQuickLinkPreference.record_access(user, quicklink)
        
        logger.debug(f"User {user.id} clicked quicklink {quicklink.id} (count: {pref.click_count})")
        
        return Response({
            'status': 'success',
            'message': 'تم تسجيل النقر',
            'data': {
                'quicklink_id': quicklink.id,
                'click_count': pref.click_count,
                'last_accessed_at': pref.last_accessed_at.isoformat()
            }
        })
    
    @action(detail=False, methods=['get'], url_path='my-preferences')
    def my_preferences(self, request):
        """
        Get current user's quick link preferences (pins and recent).
        
        GET /quicklinks/my-preferences/
        
        Returns a summary of pinned links and recent links separately.
        """
        user = request.user
        
        prefs = UserQuickLinkPreference.objects.filter(user=user).select_related('quicklink')
        
        pinned = []
        recent = []
        
        for pref in prefs:
            if not pref.quicklink.is_active:
                continue
                
            item = {
                'quicklink_id': pref.quicklink_id,
                'name': pref.quicklink.name,
                'is_pinned': pref.is_pinned,
                'pin_order': pref.pin_order,
                'last_accessed_at': pref.last_accessed_at.isoformat() if pref.last_accessed_at else None,
                'click_count': pref.click_count
            }
            
            if pref.is_pinned:
                pinned.append(item)
            elif pref.last_accessed_at:
                recent.append(item)
        
        # Sort pinned by pin_order, recent by last_accessed_at
        pinned.sort(key=lambda x: x['pin_order'])
        recent.sort(key=lambda x: x['last_accessed_at'] or '', reverse=True)
        
        return Response({
            'status': 'success',
            'message': 'User preferences retrieved successfully',
            'data': {
                'pinned_count': len(pinned),
                'recent_count': len(recent),
                'pinned': pinned,
                'recent': recent[:10]  # Limit recent to 10 items
            }
        })
