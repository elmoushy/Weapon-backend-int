"""
Models for the newsletters system with encryption support and Oracle compatibility.

This module defines the database models for newsletters with three content types
(normal news, slider news, employee achievements) and BLOB-based image storage.
"""

import hashlib
import logging
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

logger = logging.getLogger(__name__)
User = get_user_model()


class EncryptedTextField(models.TextField):
    """Custom text field that automatically encrypts/decrypts data for newsletters"""
    
    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            from .encryption import newsletters_data_encryption
            return newsletters_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt text field: {e}")
            return value
    
    def to_python(self, value):
        if not value:
            return value
        if isinstance(value, str):
            try:
                from .encryption import newsletters_data_encryption
                return newsletters_data_encryption.decrypt(value)
            except Exception as e:
                logger.error(f"Failed to decrypt text field in to_python: {e}")
                return value
        try:
            from .encryption import newsletters_data_encryption
            return newsletters_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt text field in to_python: {e}")
            return value
    
    def get_prep_value(self, value):
        if not value:
            return value
        try:
            from .encryption import newsletters_data_encryption
            if not isinstance(value, str):
                value = str(value)
            return newsletters_data_encryption.encrypt(value)
        except Exception as e:
            logger.error(f"Failed to encrypt text field: {e}")
            return value


class EncryptedCharField(models.CharField):
    """Custom char field that automatically encrypts/decrypts data for newsletters"""
    
    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            from .encryption import newsletters_data_encryption
            return newsletters_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt char field: {e}")
            return value
    
    def to_python(self, value):
        if not value:
            return value
        if isinstance(value, str):
            try:
                from .encryption import newsletters_data_encryption
                return newsletters_data_encryption.decrypt(value)
            except Exception as e:
                logger.error(f"Failed to decrypt char field in to_python: {e}")
                return value
        try:
            from .encryption import newsletters_data_encryption
            return newsletters_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt char field in to_python: {e}")
            return value
    
    def get_prep_value(self, value):
        if not value:
            return value
        try:
            from .encryption import newsletters_data_encryption
            if not isinstance(value, str):
                value = str(value)
            return newsletters_data_encryption.encrypt(value)
        except Exception as e:
            logger.error(f"Failed to encrypt char field: {e}")
            return value


class NewsletterQuerySet(models.QuerySet):
    """Custom QuerySet for Newsletter with chainable methods"""
    
    def with_images(self):
        """Prefetch related images to prevent N+1 queries"""
        return self.prefetch_related('images')
    
    def by_type(self, news_type):
        """Filter newsletters by news type"""
        return self.filter(news_type=news_type)
    
    def recent(self):
        """Return newsletters ordered by creation date (most recent first)"""
        return self.order_by('-created_at')
    
    def by_position(self):
        """Return newsletters ordered by position (ascending) then creation date"""
        return self.order_by('position', '-created_at')
    
    def filter_by_title(self, title):
        """
        Filter by title using hash field (Oracle-compatible).
        
        Args:
            title: The title to search for
            
        Returns:
            QuerySet of matching newsletters
        """
        if not title:
            return self.none()
        
        title_hash = hashlib.sha256(title.encode()).hexdigest()
        return self.filter(title_hash=title_hash)


class NewsletterManager(models.Manager):
    """Custom manager for Newsletter with Oracle-compatible hash-based queries"""
    
    def get_queryset(self):
        """Return custom QuerySet with chainable methods"""
        return NewsletterQuerySet(self.model, using=self._db)
    
    def with_images(self):
        """Prefetch related images to prevent N+1 queries"""
        return self.get_queryset().with_images()
    
    def by_type(self, news_type):
        """Filter newsletters by news type"""
        return self.get_queryset().by_type(news_type)
    
    def recent(self):
        """Return newsletters ordered by creation date (most recent first)"""
        return self.get_queryset().recent()
    
    def by_position(self):
        """Return newsletters ordered by position (ascending) then creation date"""
        return self.get_queryset().by_position()
    
    def filter_by_title(self, title):
        """
        Filter by title using hash field (Oracle-compatible).
        
        Args:
            title: The title to search for
            
        Returns:
            QuerySet of matching newsletters
        """
        return self.get_queryset().filter_by_title(title)


class Newsletter(models.Model):
    """
    Core newsletter model supporting three news types with encrypted fields.
    
    Features:
    - Three news types: NORMAL (regular news), SLIDER (homepage carousel), ACHIEVEMENT (employee highlights)
    - Encrypted title and details with hash indexes for Oracle compatibility
    - UAE timezone enforcement via middleware
    - Author tracking with foreign key to User model
    """
    
    NEWS_TYPES = [
        ('NORMAL', 'Normal News'),
        ('SLIDER', 'Slider News'),
        ('ACHIEVEMENT', 'Employee Achievement'),
    ]
    
    news_type = models.CharField(
        max_length=20,
        choices=NEWS_TYPES,
        default='NORMAL',
        db_index=True,
        help_text="Type of newsletter: NORMAL, SLIDER, or ACHIEVEMENT"
    )
    
    title = EncryptedCharField(
        max_length=500,
        help_text="Encrypted newsletter title"
    )
    
    title_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of title for searchability (Oracle-compatible)"
    )
    
    details = EncryptedTextField(
        help_text="Encrypted newsletter full details/body content"
    )
    
    details_hash = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        help_text="SHA-256 hash of details for search/filtering"
    )
    
    position = models.IntegerField(
        default=0,
        db_index=True,
        validators=[MinValueValidator(0)],
        help_text="Display order position (0-based, lower values appear first)"
    )
    
    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='newsletters',
        help_text="Newsletter creator (PROTECT prevents deletion if newsletters exist)"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Creation timestamp (UAE timezone)"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last modification timestamp (UAE timezone)"
    )
    
    objects = NewsletterManager()
    
    class Meta:
        ordering = ['position', '-created_at']
        indexes = [
            models.Index(fields=['news_type', 'position', '-created_at']),
            models.Index(fields=['author', '-created_at']),
        ]
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate hash fields"""
        if self.title:
            self.title_hash = hashlib.sha256(self.title.encode()).hexdigest()
        
        if self.details:
            self.details_hash = hashlib.sha256(self.details.encode()).hexdigest()
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.get_news_type_display()}: {self.title[:50]}"


class NewsletterImageManager(models.Manager):
    """Custom manager for NewsletterImage with optimized queries"""
    
    def main_images(self):
        """Filter for main/cover images only"""
        return self.filter(is_main=True)
    
    def gallery_images(self):
        """Filter for gallery images (not main), ordered by display_order"""
        return self.filter(is_main=False).order_by('display_order')
    
    def for_newsletter(self, newsletter_id):
        """Get all images for a newsletter, ordered by display_order"""
        return self.filter(newsletter_id=newsletter_id).order_by('display_order')
    
    def optimized_query(self, include_full=True, include_thumbnail=True):
        """
        Select only required BLOB fields to optimize query performance.
        
        Args:
            include_full: Include file_data field
            include_thumbnail: Include thumbnail_data field
            
        Returns:
            QuerySet with deferred BLOB fields
        """
        defer_fields = []
        if not include_full:
            defer_fields.append('file_data')
        if not include_thumbnail:
            defer_fields.append('thumbnail_data')
        
        if defer_fields:
            return self.defer(*defer_fields)
        return self.all()


class NewsletterImage(models.Model):
    """
    BLOB-based image storage for newsletters with automatic optimization.
    
    Features:
    - BLOB storage (no filesystem dependencies)
    - Automatic image optimization (max 1920px width, JPEG quality 75%)
    - Automatic thumbnail generation (300x300px, JPEG quality 60%)
    - Main image tracking (one per newsletter)
    - Gallery ordering support
    """
    
    newsletter = models.ForeignKey(
        Newsletter,
        on_delete=models.CASCADE,
        related_name='images',
        help_text="Parent newsletter (CASCADE deletes images when newsletter deleted)"
    )
    
    file_data = models.BinaryField(
        help_text="Optimized full image (JPEG, max 1920px width, quality 75%, max 10MB)"
    )
    
    thumbnail_data = models.BinaryField(
        null=True,
        blank=True,
        help_text="Thumbnail (300x300px, JPEG quality 60%, max 500KB)"
    )
    
    original_filename = models.CharField(
        max_length=255,
        help_text="Sanitized original filename (stored for display)"
    )
    
    file_size = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="File size in bytes (for quota tracking)"
    )
    
    mime_type = models.CharField(
        max_length=100,
        default='image/jpeg',
        help_text="MIME type: image/jpeg, image/png, image/webp"
    )
    
    is_main = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Main/cover image flag (only one per newsletter)"
    )
    
    display_order = models.IntegerField(
        default=0,
        db_index=True,
        validators=[MinValueValidator(0)],
        help_text="Order of images in gallery (0-based, main image = 0)"
    )
    
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Upload timestamp (UAE timezone)"
    )
    
    objects = NewsletterImageManager()
    
    class Meta:
        ordering = ['display_order', 'uploaded_at']
        indexes = [
            models.Index(fields=['newsletter', 'display_order']),
            models.Index(fields=['newsletter', 'is_main']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['newsletter', 'is_main'],
                condition=models.Q(is_main=True),
                name='unique_main_image_per_newsletter'
            )
        ]
    
    def save(self, *args, **kwargs):
        """Override save to enforce only one main image per newsletter"""
        if self.is_main:
            # Set other images for this newsletter to not be main
            NewsletterImage.objects.filter(
                newsletter=self.newsletter,
                is_main=True
            ).exclude(pk=self.pk).update(is_main=False)
            
            # Main image should have display_order = 0
            if self.display_order != 0:
                self.display_order = 0
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        main_indicator = " (Main)" if self.is_main else ""
        return f"{self.newsletter.title[:30]} - {self.original_filename}{main_indicator}"
