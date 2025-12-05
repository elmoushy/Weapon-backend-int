"""
Models for the quicklinks system with BLOB icon storage.

This module defines the database model for Quick Links with:
- BLOB-based icon storage (no filesystem dependencies)
- SVG and optimized image support
- Oracle and SQLite compatibility
"""

import logging
from django.db import models
from django.core.validators import MinValueValidator, URLValidator
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class QuickLinkQuerySet(models.QuerySet):
    """Custom QuerySet for QuickLink with chainable methods"""
    
    def active(self):
        """Filter for active quick links only"""
        return self.filter(is_active=True)
    
    def by_position(self):
        """Return quick links ordered by position (ascending)"""
        return self.order_by('position', '-created_at')
    
    def inactive(self):
        """Filter for inactive quick links only"""
        return self.filter(is_active=False)


class QuickLinkManager(models.Manager):
    """Custom manager for QuickLink with optimized queries"""
    
    def get_queryset(self):
        """Return custom QuerySet with chainable methods"""
        return QuickLinkQuerySet(self.model, using=self._db)
    
    def active(self):
        """Get only active quick links"""
        return self.get_queryset().active()
    
    def by_position(self):
        """Get quick links ordered by position"""
        return self.get_queryset().by_position()
    
    def get_next_position(self):
        """
        Get the next available position number.
        
        Returns:
            int: Next available position (0-based)
        """
        max_position = self.aggregate(max_pos=models.Max('position'))['max_pos']
        return (max_position or -1) + 1
    
    def optimized_list(self, include_icon=False):
        """
        Get quick links with optimized BLOB handling.
        
        Args:
            include_icon: Whether to include icon_data (BLOB field)
            
        Returns:
            QuerySet with deferred BLOB field if not needed
        """
        if include_icon:
            return self.get_queryset()
        return self.get_queryset().defer('icon_data')


class QuickLink(models.Model):
    """
    Quick Link model for external application shortcuts.
    
    Features:
    - BLOB-based icon storage (SVG, PNG, JPG, WEBP)
    - Automatic position management
    - Active/inactive status for visibility control
    - Oracle and SQLite compatibility
    """
    
    name = models.CharField(
        max_length=100,
        help_text="Display name for the quick link (max 100 characters)"
    )
    
    icon_data = models.BinaryField(
        null=True,
        blank=True,
        help_text="Icon image data stored as BLOB (PNG, JPG, SVG, WEBP - max 5MB)"
    )
    
    icon_mime_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="MIME type of the icon: image/png, image/jpeg, image/svg+xml, image/webp"
    )
    
    icon_original_filename = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Original filename of uploaded icon (sanitized)"
    )
    
    redirect_url = models.CharField(
        max_length=1000,  # Reduced from 2048 for Oracle compatibility (VARCHAR2 limit with UTF-8)
        validators=[URLValidator()],
        help_text="External URL to redirect to when clicking the link"
    )
    
    position = models.IntegerField(
        default=0,
        db_index=True,
        validators=[MinValueValidator(0)],
        help_text="Display order position (0-based, lower values appear first)"
    )
    
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the link is visible to users"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_quicklinks',
        help_text="User who created this quick link"
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
    
    objects = QuickLinkManager()
    
    class Meta:
        ordering = ['position', '-created_at']
        verbose_name = "Quick Link"
        verbose_name_plural = "Quick Links"
        indexes = [
            models.Index(fields=['position', '-created_at']),
            models.Index(fields=['is_active', 'position']),
        ]
    
    def save(self, *args, **kwargs):
        """Override save to auto-assign position if not set"""
        if self._state.adding and self.position == 0:
            # Auto-assign next position for new records
            existing_positions = set(
                QuickLink.objects.values_list('position', flat=True)
            )
            
            # Find the lowest unused position (starting from 0)
            next_position = 0
            while next_position in existing_positions:
                next_position += 1
            
            self.position = next_position
        
        super().save(*args, **kwargs)
    
    def clear_icon(self):
        """Remove the icon from this quick link"""
        self.icon_data = None
        self.icon_mime_type = None
        self.icon_original_filename = None
        self.save(update_fields=['icon_data', 'icon_mime_type', 'icon_original_filename', 'updated_at'])
    
    @property
    def has_icon(self):
        """Check if this quick link has an icon"""
        return bool(self.icon_data)
    
    def __str__(self):
        status = "✓" if self.is_active else "✗"
        return f"[{status}] {self.name} (pos: {self.position})"
