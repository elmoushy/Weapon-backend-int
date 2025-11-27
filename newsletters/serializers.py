"""
Serializers for the newsletters system.

This module provides serializers for Newsletter and NewsletterImage models
with support for image URL generation and encrypted field handling.
"""

from rest_framework import serializers
from django.urls import reverse
from .models import Newsletter, NewsletterImage


class NewsletterImageSerializer(serializers.ModelSerializer):
    """
    Serializer for NewsletterImage with URL-based access (not Base64).
    
    Returns image URLs for download/thumbnail endpoints instead of
    embedding binary data in JSON responses.
    """
    
    download_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = NewsletterImage
        fields = [
            'id',
            'original_filename',
            'file_size',
            'mime_type',
            'is_main',
            'display_order',
            'uploaded_at',
            'download_url',
            'thumbnail_url'
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_size', 'mime_type']
    
    def get_download_url(self, obj):
        """Generate URL for downloading full image"""
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                reverse('newsletter-image-download', kwargs={'pk': obj.pk})
            )
        return None
    
    def get_thumbnail_url(self, obj):
        """Generate URL for downloading thumbnail"""
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                reverse('newsletter-image-thumbnail', kwargs={'pk': obj.pk})
            )
        return None


class NewsletterSerializer(serializers.ModelSerializer):
    """
    Serializer for Newsletter with encrypted fields and image handling.
    
    Features:
    - Automatic encryption/decryption via model fields
    - Image URLs (not Base64) for efficient API responses
    - Author information included
    - Read-only fields properly configured
    """
    
    author_name = serializers.CharField(source='author.username', read_only=True)
    images = NewsletterImageSerializer(many=True, read_only=True)
    main_image = serializers.SerializerMethodField()
    
    class Meta:
        model = Newsletter
        fields = [
            'id',
            'news_type',
            'title',
            'details',
            'position',
            'author',
            'author_name',
            'created_at',
            'updated_at',
            'images',
            'main_image'
        ]
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']
        extra_kwargs = {
            'title': {'required': True},
            'details': {'required': True},
        }
    
    def get_main_image(self, obj):
        """Get main/cover image if it exists"""
        main_image = obj.images.filter(is_main=True).first()
        if main_image:
            return NewsletterImageSerializer(main_image, context=self.context).data
        return None
    
    def validate_news_type(self, value):
        """Validate news_type is one of allowed choices"""
        allowed_types = dict(Newsletter.NEWS_TYPES).keys()
        if value not in allowed_types:
            raise serializers.ValidationError(
                f"Invalid news_type. Allowed: {', '.join(allowed_types)}"
            )
        return value


class NewsletterCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating newsletters (without images field in input).
    Images are uploaded separately via upload endpoint.
    Position is auto-assigned by backend - any frontend value is ignored.
    """
    
    class Meta:
        model = Newsletter
        fields = ['id', 'news_type', 'title', 'details', 'position', 'author', 'author_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'author_name', 'position', 'created_at', 'updated_at']
        extra_kwargs = {
            'title': {'required': True},
            'details': {'required': True},
        }
    
    author_name = serializers.CharField(source='author.username', read_only=True)
    
    def create(self, validated_data):
        """Create newsletter with current user as author"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['author'] = request.user
        return super().create(validated_data)


class NewsletterImageUploadSerializer(serializers.Serializer):
    """
    Serializer for uploading images to newsletters.
    
    Handles file validation and processing via image_utils.
    """
    
    image = serializers.ImageField(required=True)
    is_main = serializers.BooleanField(default=False)
    display_order = serializers.IntegerField(default=0, min_value=0)
    
    def validate_image(self, value):
        """Validate image using security utils"""
        from .image_utils import validate_image_file
        
        # Validate returns (mime_type, file_size, sanitized_name)
        # Just check it passes validation, actual processing happens in view
        validate_image_file(value)
        
        return value
