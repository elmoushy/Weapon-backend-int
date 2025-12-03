"""
Serializers for the quicklinks system.

This module provides serializers for QuickLink model with:
- URL-based icon access
- Icon upload handling
- Bulk position update support
"""

from rest_framework import serializers
from django.urls import reverse
from .models import QuickLink


class QuickLinkSerializer(serializers.ModelSerializer):
    """
    Serializer for QuickLink with URL-based icon access.
    
    Returns icon URL for download endpoint instead of
    embedding binary data in JSON responses.
    """
    
    icon_url = serializers.SerializerMethodField()
    
    class Meta:
        model = QuickLink
        fields = [
            'id',
            'name',
            'icon_url',
            'redirect_url',
            'position',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'icon_url', 'created_at', 'updated_at']
    
    def get_icon_url(self, obj):
        """Generate URL for downloading icon if it exists"""
        if not obj.has_icon:
            return None
        
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                reverse('quicklink-icon', kwargs={'pk': obj.pk})
            )
        return None


class QuickLinkCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating quick links.
    Icon is uploaded separately via dedicated endpoint.
    Position is auto-assigned by backend if not provided.
    """
    
    class Meta:
        model = QuickLink
        fields = [
            'id',
            'name',
            'redirect_url',
            'position',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'name': {'required': True},
            'redirect_url': {'required': True},
            'position': {'required': False},
            'is_active': {'required': False, 'default': True},
        }
    
    def validate_name(self, value):
        """Validate name length"""
        if len(value) > 100:
            raise serializers.ValidationError(
                "Name must be 100 characters or less."
            )
        return value
    
    def validate_redirect_url(self, value):
        """Validate URL format"""
        if not value:
            raise serializers.ValidationError("URL is required.")
        
        # Basic URL validation (URLValidator in model handles the rest)
        if not (value.startswith('http://') or value.startswith('https://')):
            raise serializers.ValidationError(
                "Enter a valid URL starting with http:// or https://"
            )
        
        return value


class QuickLinkUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating quick links.
    Supports partial updates.
    """
    
    icon_url = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = QuickLink
        fields = [
            'id',
            'name',
            'icon_url',
            'redirect_url',
            'position',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'icon_url', 'created_at', 'updated_at']
    
    def get_icon_url(self, obj):
        """Generate URL for downloading icon if it exists"""
        if not obj.has_icon:
            return None
        
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                reverse('quicklink-icon', kwargs={'pk': obj.pk})
            )
        return None
    
    def validate_name(self, value):
        """Validate name length"""
        if value and len(value) > 100:
            raise serializers.ValidationError(
                "Name must be 100 characters or less."
            )
        return value


class QuickLinkIconUploadSerializer(serializers.Serializer):
    """
    Serializer for uploading icons to quick links.
    
    Handles file validation via image_utils.
    """
    
    icon = serializers.FileField(required=True)
    
    def validate_icon(self, value):
        """Validate icon file using image utilities"""
        from .image_utils import validate_icon_file
        
        try:
            validate_icon_file(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))
        
        return value


class PositionItemSerializer(serializers.Serializer):
    """Serializer for a single position update item"""
    id = serializers.IntegerField()
    position = serializers.IntegerField(min_value=0)


class BulkPositionUpdateSerializer(serializers.Serializer):
    """
    Serializer for bulk position updates.
    
    Accepts an array of position objects and validates them.
    """
    
    positions = PositionItemSerializer(many=True)
    
    def validate_positions(self, value):
        """Validate positions list"""
        if not value:
            raise serializers.ValidationError(
                "At least one position update is required."
            )
        
        # Check for duplicate IDs
        ids = [item['id'] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Duplicate quick link IDs in position updates."
            )
        
        # Check for duplicate positions
        positions = [item['position'] for item in value]
        if len(positions) != len(set(positions)):
            raise serializers.ValidationError(
                "Duplicate positions in position updates."
            )
        
        return value
