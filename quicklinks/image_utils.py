"""
Image optimization utilities for quicklinks icons.

This module provides icon processing functionality including:
- Image optimization (resize, compress)
- SVG handling and conversion
- Integration with security validation utilities
"""

import io
import logging
from PIL import Image
from django.core.exceptions import ValidationError
from weaponpowercloud_backend.utils.security_utils import (
    validate_file_size,
    sanitize_filename
)

logger = logging.getLogger(__name__)

# Icon optimization settings
MAX_ICON_SIZE = 256  # Max width/height for icons
ICON_QUALITY = 85  # PNG/JPEG quality for icons
MAX_ICON_FILE_SIZE_MB = 5  # Maximum file size in MB

# Allowed icon formats and MIME types
ALLOWED_ICON_FORMATS = {'PNG', 'JPEG', 'WEBP', 'SVG'}
ALLOWED_ICON_MIMES = {
    'image/png': 'PNG',
    'image/jpeg': 'JPEG',
    'image/jpg': 'JPEG',
    'image/webp': 'WEBP',
    'image/svg+xml': 'SVG',
}


def validate_icon_file(file):
    """
    Validate uploaded icon file.
    
    Args:
        file: Django UploadedFile object
        
    Returns:
        tuple: (mime_type, file_size, sanitized_filename)
        
    Raises:
        ValidationError: If file is invalid or not an allowed image type
    """
    # Check file size first
    try:
        # Handle BytesIO objects that don't have a size attribute
        if hasattr(file, 'size'):
            file_size = validate_file_size(file, max_size_mb=MAX_ICON_FILE_SIZE_MB)
        else:
            # For BytesIO or file-like objects without size attribute
            current_pos = file.tell()
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(current_pos)  # Seek back
            
            max_size_bytes = MAX_ICON_FILE_SIZE_MB * 1024 * 1024
            if file_size > max_size_bytes:
                raise ValidationError(f"File too large. Maximum size: {MAX_ICON_FILE_SIZE_MB}MB")
    except ValidationError as e:
        raise ValidationError(f"File too large. Maximum size: {MAX_ICON_FILE_SIZE_MB}MB")
    
    # Get file name
    filename = getattr(file, 'name', 'unknown')
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    # Determine MIME type from extension and content
    content_type = getattr(file, 'content_type', None)
    
    # Handle SVG files specially
    if ext == 'svg' or content_type == 'image/svg+xml':
        # Read first bytes to verify SVG content
        file.seek(0)
        header = file.read(1024).decode('utf-8', errors='ignore').lower()
        file.seek(0)
        
        if '<svg' in header or '<?xml' in header:
            sanitized_name = sanitize_filename(filename)
            logger.info(f"SVG icon validated: {sanitized_name} ({file_size / 1024:.1f}KB)")
            return 'image/svg+xml', file_size, sanitized_name
        else:
            raise ValidationError("Invalid SVG file format")
    
    # For other image types, validate using PIL
    try:
        file.seek(0)
        img = Image.open(file)
        img_format = img.format
        file.seek(0)
        
        if img_format not in {'PNG', 'JPEG', 'WEBP'}:
            raise ValidationError(
                f"Invalid image format '{img_format}'. "
                f"Allowed: PNG, JPG, JPEG, SVG, WEBP"
            )
        
        # Determine MIME type
        mime_map = {
            'PNG': 'image/png',
            'JPEG': 'image/jpeg',
            'WEBP': 'image/webp',
        }
        mime_type = mime_map.get(img_format, 'image/png')
        
    except Exception as e:
        logger.error(f"Image validation failed: {e}")
        raise ValidationError(f"Invalid image file: {str(e)}")
    
    # Sanitize filename
    try:
        sanitized_name = sanitize_filename(filename)
    except ValidationError:
        sanitized_name = f"icon.{ext}" if ext else "icon"
    
    logger.info(f"Icon validated: {sanitized_name} ({mime_type}, {file_size / 1024:.1f}KB)")
    
    return mime_type, file_size, sanitized_name


def optimize_icon(image_file, target_size=MAX_ICON_SIZE):
    """
    Optimize icon for storage with size reduction and quality optimization.
    
    Features:
    - Resize to max 256px while maintaining aspect ratio
    - Convert to PNG format for transparency support
    - Optimize for small file size
    
    Args:
        image_file: Django UploadedFile object or file-like object
        target_size: Maximum width/height for the icon (default 256)
        
    Returns:
        tuple: (bytes: optimized icon data, str: mime_type)
        
    Raises:
        ValidationError: If image processing fails
    """
    try:
        # Check if it's an SVG file
        image_file.seek(0)
        header = image_file.read(100)
        image_file.seek(0)
        
        # Check for SVG
        header_str = header.decode('utf-8', errors='ignore').lower()
        if '<svg' in header_str or '<?xml' in header_str:
            # Return SVG as-is (no conversion needed)
            return process_svg_icon(image_file)
        
        # Open image with PIL
        image = Image.open(image_file)
        original_format = image.format
        
        # Get original dimensions
        original_width, original_height = image.size
        logger.debug(f"Original icon size: {original_width}x{original_height}")
        
        # Calculate new dimensions while maintaining aspect ratio
        if original_width > target_size or original_height > target_size:
            # Calculate scale factor to fit within target_size
            scale = min(target_size / original_width, target_size / original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            
            # Resize with high-quality Lanczos filter
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Icon resized: {original_width}x{original_height} → {new_width}x{new_height}")
        
        # Convert to RGBA for transparency support, then to PNG
        if image.mode not in ('RGBA', 'RGB'):
            if image.mode == 'P':
                # Handle palette mode with transparency
                if 'transparency' in image.info:
                    image = image.convert('RGBA')
                else:
                    image = image.convert('RGB')
            elif image.mode in ('LA', 'PA'):
                image = image.convert('RGBA')
            else:
                image = image.convert('RGB')
        
        # Save to bytes buffer as PNG for transparency support
        output = io.BytesIO()
        
        if image.mode == 'RGBA':
            # Keep transparency with PNG
            image.save(output, format='PNG', optimize=True)
            mime_type = 'image/png'
        else:
            # No transparency, can use WEBP for better compression
            image.save(output, format='WEBP', quality=ICON_QUALITY, optimize=True)
            mime_type = 'image/webp'
        
        optimized_data = output.getvalue()
        optimized_size = len(optimized_data)
        
        logger.info(f"Icon optimized: {optimized_size / 1024:.1f}KB ({mime_type})")
        
        return optimized_data, mime_type
        
    except Exception as e:
        logger.error(f"Icon optimization failed: {e}")
        raise ValidationError(f"Failed to process icon: {str(e)}")


def process_svg_icon(file):
    """
    Process SVG icon file.
    
    SVG files are passed through with minimal processing:
    - Validate SVG structure
    - Clean dangerous elements (scripts, etc.)
    - Return optimized SVG bytes
    
    Args:
        file: File-like object containing SVG data
        
    Returns:
        tuple: (bytes: SVG data, str: 'image/svg+xml')
        
    Raises:
        ValidationError: If SVG is invalid or contains dangerous content
    """
    try:
        file.seek(0)
        svg_content = file.read()
        
        if isinstance(svg_content, bytes):
            svg_str = svg_content.decode('utf-8')
        else:
            svg_str = svg_content
        
        # Basic SVG validation
        svg_lower = svg_str.lower()
        
        if '<svg' not in svg_lower:
            raise ValidationError("Invalid SVG file: missing <svg> element")
        
        # Security: Remove dangerous elements
        dangerous_elements = [
            '<script', '</script>',
            'javascript:', 'vbscript:',
            'onload=', 'onerror=', 'onclick=', 'onmouseover=',
            '<iframe', '</iframe>',
            '<embed', '</embed>',
            '<object', '</object>',
        ]
        
        for dangerous in dangerous_elements:
            if dangerous in svg_lower:
                logger.warning(f"Dangerous SVG content detected: {dangerous}")
                raise ValidationError("SVG file contains potentially dangerous content")
        
        # Return cleaned SVG
        svg_bytes = svg_str.encode('utf-8')
        
        logger.info(f"SVG icon processed: {len(svg_bytes) / 1024:.1f}KB")
        
        return svg_bytes, 'image/svg+xml'
        
    except UnicodeDecodeError:
        raise ValidationError("Invalid SVG file: encoding error")
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"SVG processing failed: {e}")
        raise ValidationError(f"Failed to process SVG: {str(e)}")


def process_quicklink_icon(file):
    """
    Process uploaded icon file for a quick link.
    
    This is the main entry point for icon processing:
    1. Validates the file (type, size)
    2. Optimizes or processes based on format
    3. Returns processed data ready for storage
    
    Args:
        file: Django UploadedFile object
        
    Returns:
        dict: {
            'icon_data': bytes,
            'mime_type': str,
            'original_filename': str,
            'file_size': int
        }
        
    Raises:
        ValidationError: If file is invalid or processing fails
    """
    # Validate file
    mime_type, file_size, sanitized_filename = validate_icon_file(file)
    
    # Process based on type
    if mime_type == 'image/svg+xml':
        icon_data, final_mime = process_svg_icon(file)
    else:
        icon_data, final_mime = optimize_icon(file)
    
    return {
        'icon_data': icon_data,
        'mime_type': final_mime,
        'original_filename': sanitized_filename,
        'file_size': len(icon_data)
    }
