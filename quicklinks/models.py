"""
Models for the quicklinks system with BLOB icon storage.

This module defines the database model for Quick Links with:
- BLOB-based icon storage (no filesystem dependencies)
- SVG and optimized image support
- Oracle and SQLite compatibility
- User-specific pins and recent access tracking
"""

import logging
from django.db import models
from django.core.validators import MinValueValidator, URLValidator
from django.contrib.auth import get_user_model
from django.utils import timezone

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


class UserQuickLinkPreference(models.Model):
    """
    User-specific preferences for quick links.
    
    Tracks:
    - Pinned links per user
    - Last access time per link for recent ordering
    - Click count for analytics
    
    The ordering logic is: Pinned first (by pin_order), then by last_accessed_at (recent first)
    """
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quicklink_preferences',
        help_text="User who owns this preference"
    )
    
    quicklink = models.ForeignKey(
        QuickLink,
        on_delete=models.CASCADE,
        related_name='user_preferences',
        help_text="Quick link this preference applies to"
    )
    
    is_pinned = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the user has pinned this quick link"
    )
    
    pin_order = models.IntegerField(
        default=0,
        help_text="Order among pinned items (lower = first)"
    )
    
    last_accessed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Last time user clicked/accessed this link"
    )
    
    click_count = models.IntegerField(
        default=0,
        help_text="Total click count for this link by this user"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this preference was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp"
    )
    
    class Meta:
        unique_together = ['user', 'quicklink']
        ordering = ['-is_pinned', 'pin_order', '-last_accessed_at']
        verbose_name = "User Quick Link Preference"
        verbose_name_plural = "User Quick Link Preferences"
        indexes = [
            models.Index(fields=['user', '-is_pinned', 'pin_order']),
            models.Index(fields=['user', '-last_accessed_at']),
        ]
    
    def __str__(self):
        pinned = "📌" if self.is_pinned else ""
        return f"{self.user.email} - {self.quicklink.name} {pinned}"
    
    @classmethod
    def record_access(cls, user, quicklink):
        """
        Record a user accessing (clicking) a quick link.
        Creates preference if it doesn't exist.
        
        Args:
            user: User who accessed the link
            quicklink: QuickLink that was accessed
            
        Returns:
            UserQuickLinkPreference instance
        """
        pref, created = cls.objects.get_or_create(
            user=user,
            quicklink=quicklink,
            defaults={
                'last_accessed_at': timezone.now(),
                'click_count': 1
            }
        )
        
        if not created:
            pref.last_accessed_at = timezone.now()
            pref.click_count += 1
            pref.save(update_fields=['last_accessed_at', 'click_count', 'updated_at'])
        
        return pref
    
    @classmethod
    def toggle_pin(cls, user, quicklink):
        """
        Toggle pin status for a quick link.
        
        Args:
            user: User toggling the pin
            quicklink: QuickLink to pin/unpin
            
        Returns:
            tuple: (UserQuickLinkPreference, is_now_pinned)
        """
        pref, created = cls.objects.get_or_create(
            user=user,
            quicklink=quicklink
        )
        
        pref.is_pinned = not pref.is_pinned
        
        if pref.is_pinned:
            # Assign next pin order
            max_order = cls.objects.filter(
                user=user, 
                is_pinned=True
            ).aggregate(max_order=models.Max('pin_order'))['max_order']
            pref.pin_order = (max_order or -1) + 1
        else:
            pref.pin_order = 0
        
        pref.save(update_fields=['is_pinned', 'pin_order', 'updated_at'])
        
        return pref, pref.is_pinned
    
    @classmethod
    def get_ordered_quicklinks_for_user(cls, user, queryset=None):
        """
        Get quick links ordered by user preference:
        1. Pinned first (by pin_order)
        2. Recently accessed
        3. Remaining by default position
        
        Args:
            user: User to get preferences for
            queryset: Base QuickLink queryset (optional)
            
        Returns:
            List of QuickLink objects with user preference data
        """
        from django.db.models import Case, When, Value, IntegerField, F
        from django.db.models.functions import Coalesce
        
        if queryset is None:
            queryset = QuickLink.objects.active().defer('icon_data')
        
        # Get user preferences
        user_prefs = {
            pref.quicklink_id: pref 
            for pref in cls.objects.filter(user=user).select_related('quicklink')
        }
        
        # Annotate quicklinks with user preference data
        quicklink_ids_pinned = [
            qid for qid, pref in user_prefs.items() if pref.is_pinned
        ]
        quicklink_ids_accessed = [
            qid for qid, pref in user_prefs.items() 
            if pref.last_accessed_at and not pref.is_pinned
        ]
        
        # Create ordering cases
        # Priority: 0 = pinned, 1 = recently accessed, 2 = others
        queryset = queryset.annotate(
            user_priority=Case(
                When(id__in=quicklink_ids_pinned, then=Value(0)),
                When(id__in=quicklink_ids_accessed, then=Value(1)),
                default=Value(2),
                output_field=IntegerField()
            )
        )
        
        # Get all quicklinks
        quicklinks = list(queryset)
        
        # Sort with custom key
        def sort_key(ql):
            pref = user_prefs.get(ql.id)
            if pref and pref.is_pinned:
                # Pinned: priority 0, then by pin_order
                return (0, pref.pin_order, 0)
            elif pref and pref.last_accessed_at:
                # Recently accessed: priority 1, then by last_accessed (newer first)
                # Use negative timestamp for descending order
                timestamp = pref.last_accessed_at.timestamp() if pref.last_accessed_at else 0
                return (1, 0, -timestamp)
            else:
                # Others: priority 2, then by position
                return (2, ql.position, 0)
        
        quicklinks.sort(key=sort_key)
        
        return quicklinks, user_prefs
