"""
Image optimization utilities for newsletters.

This module provides image processing functionality including:
- Image optimization (resize, compress, progressive encoding)
- Thumbnail generation
- Integration with security validation utilities
"""

import io
import logging
from PIL import Image
from django.core.exceptions import ValidationError
from weaponpowercloud_backend.utils.security_utils import (
    validate_file_type,
    validate_file_size,
    sanitize_filename
)

logger = logging.getLogger(__name__)

# Image optimization settings
MAX_IMAGE_WIDTH = 1920  # Max width for full images
MAX_IMAGE_HEIGHT = 1080  # Max height for full images
IMAGE_QUALITY = 75  # JPEG quality for full images

THUMBNAIL_SIZE = (300, 300)  # Thumbnail dimensions
THUMBNAIL_QUALITY = 60  # JPEG quality for thumbnails

# Allowed image formats
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
ALLOWED_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/webp'}


def validate_image_file(file):
    """
    Validate uploaded image file using security utils.
    
    Args:
        file: Django UploadedFile object
        
    Returns:
        tuple: (mime_type, file_size, sanitized_filename)
        
    Raises:
        ValidationError: If file is invalid or not an image
    """
    # Validate file type (checks magic bytes)
    mime_type = validate_file_type(file)
    
    # Ensure it's an image
    if mime_type not in ALLOWED_IMAGE_MIMES:
        raise ValidationError(
            f"File type '{mime_type}' is not a valid image. "
            f"Allowed: JPEG, PNG, WebP"
        )
    
    # Validate file size (10MB max)
    file_size = validate_file_size(file, max_size_mb=10)
    
    # Sanitize filename
    sanitized_name = sanitize_filename(file.name)
    
    logger.info(f"Image validated: {sanitized_name} ({mime_type}, {file_size / 1024:.1f}KB)")
    
    return mime_type, file_size, sanitized_name


def optimize_image_for_storage(image_file):
    """
    Optimize image for storage with size reduction and quality optimization.
    
    Features:
    - Resize to max 1920px width while maintaining aspect ratio
    - Convert to JPEG with quality 75% (good balance of size/quality)
    - Progressive encoding for faster web loading
    - Remove EXIF metadata to reduce size
    
    Args:
        image_file: Django UploadedFile object or file-like object
        
    Returns:
        bytes: Optimized image data as bytes
        
    Raises:
        ValidationError: If image processing fails
    """
    try:
        # Open image with PIL
        image = Image.open(image_file)
        
        # Convert to RGB if necessary (handles RGBA, P, LA modes)
        if image.mode not in ('RGB', 'L'):
            # If has alpha channel, paste on white background
            if image.mode in ('RGBA', 'LA', 'PA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1])  # Alpha channel as mask
                image = background
            else:
                image = image.convert('RGB')
        
        # Get original dimensions
        original_width, original_height = image.size
        logger.debug(f"Original image size: {original_width}x{original_height}")
        
        # Calculate new dimensions while maintaining aspect ratio
        if original_width > MAX_IMAGE_WIDTH or original_height > MAX_IMAGE_HEIGHT:
            # Calculate scale factor
            width_scale = MAX_IMAGE_WIDTH / original_width
            height_scale = MAX_IMAGE_HEIGHT / original_height
            scale = min(width_scale, height_scale)
            
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            
            # Resize with high-quality Lanczos filter
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Image resized: {original_width}x{original_height} → {new_width}x{new_height}")
        
        # Save to bytes buffer with optimization
        output = io.BytesIO()
        image.save(
            output,
            format='JPEG',
            quality=IMAGE_QUALITY,
            optimize=True,  # Enable extra optimization passes
            progressive=True,  # Progressive JPEG for faster web loading
        )
        
        optimized_data = output.getvalue()
        optimized_size = len(optimized_data)
        
        logger.info(f"Image optimized: {optimized_size / 1024:.1f}KB")
        
        return optimized_data
        
    except Exception as e:
        logger.error(f"Image optimization failed: {e}")
        raise ValidationError(f"Failed to process image: {str(e)}")


def create_thumbnail(image_file, size=THUMBNAIL_SIZE):
    """
    Generate thumbnail from image.
    
    Creates a square thumbnail by:
    1. Cropping to square (center crop)
    2. Resizing to target size (default 300x300)
    3. Compressing with JPEG quality 60%
    
    Args:
        image_file: Django UploadedFile object or file-like object
        size: Tuple of (width, height) for thumbnail (default 300x300)
        
    Returns:
        bytes: Thumbnail image data as bytes
        
    Raises:
        ValidationError: If thumbnail generation fails
    """
    try:
        # Open image with PIL
        image = Image.open(image_file)
        
        # Convert to RGB if necessary
        if image.mode not in ('RGB', 'L'):
            if image.mode in ('RGBA', 'LA', 'PA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1])
                image = background
            else:
                image = image.convert('RGB')
        
        # Get original dimensions
        width, height = image.size
        
        # Calculate crop box for center square
        if width > height:
            # Landscape - crop sides
            left = (width - height) // 2
            right = left + height
            top = 0
            bottom = height
        else:
            # Portrait or square - crop top/bottom
            top = (height - width) // 2
            bottom = top + width
            left = 0
            right = width
        
        # Crop to square
        image = image.crop((left, top, right, bottom))
        
        # Resize to thumbnail size
        image.thumbnail(size, Image.Resampling.LANCZOS)
        
        # Save to bytes buffer
        output = io.BytesIO()
        image.save(
            output,
            format='JPEG',
            quality=THUMBNAIL_QUALITY,
            optimize=True
        )
        
        thumbnail_data = output.getvalue()
        thumbnail_size = len(thumbnail_data)
        
        logger.info(f"Thumbnail created: {thumbnail_size / 1024:.1f}KB")
        
        return thumbnail_data
        
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise ValidationError(f"Failed to generate thumbnail: {str(e)}")


def process_newsletter_image(image_file):
    """
    Process uploaded newsletter image: validate, optimize, and create thumbnail.
    
    This is the main entry point for image processing. It handles:
    1. Security validation (file type, size, filename)
    2. Image optimization for storage
    3. Thumbnail generation
    
    Args:
        image_file: Django UploadedFile object
        
    Returns:
        dict: {
            'file_data': bytes,  # Optimized full image
            'thumbnail_data': bytes,  # Thumbnail
            'mime_type': str,  # MIME type
            'file_size': int,  # Original file size
            'original_filename': str  # Sanitized filename
        }
        
    Raises:
        ValidationError: If validation or processing fails
    """
    # Step 1: Validate image
    mime_type, file_size, sanitized_name = validate_image_file(image_file)
    
    # Reset file pointer after validation
    image_file.seek(0)
    
    # Step 2: Optimize full image
    optimized_data = optimize_image_for_storage(image_file)
    
    # Reset file pointer for thumbnail generation
    image_file.seek(0)
    
    # Step 3: Create thumbnail
    thumbnail_data = create_thumbnail(image_file)
    
    return {
        'file_data': optimized_data,
        'thumbnail_data': thumbnail_data,
        'mime_type': mime_type,
        'file_size': len(optimized_data),  # Use optimized size, not original
        'original_filename': sanitized_name
    }
