"""
URL utilities for fixing mixed content issues.

When Django is behind a reverse proxy that terminates SSL,
request.build_absolute_uri() may generate http:// URLs even when
the client accessed the site via https://.

This module provides utilities to ensure HTTPS URLs are generated
in production environments.
"""

from django.urls import reverse


def is_localhost(host):
    """Check if the host is a localhost address."""
    return (
        host.startswith('localhost') or 
        host.startswith('127.0.0.1') or
        host.startswith('0.0.0.0')
    )


def force_https(url, request):
    """
    Force HTTPS for non-localhost URLs.
    
    This fixes mixed content issues when behind a reverse proxy
    that doesn't properly forward the X-Forwarded-Proto header.
    
    Args:
        url: The URL string to potentially modify
        request: The Django request object
        
    Returns:
        The URL with https:// if in production, original URL otherwise
    """
    if not url or not request:
        return url
    
    host = request.get_host()
    if url.startswith('http://') and not is_localhost(host):
        return url.replace('http://', 'https://', 1)
    
    return url


def build_absolute_uri_https(request, path_or_url_name, kwargs=None, use_reverse=True):
    """
    Build an absolute URI ensuring HTTPS in production.
    
    This is a drop-in replacement for request.build_absolute_uri()
    that fixes mixed content issues.
    
    Args:
        request: The Django request object
        path_or_url_name: Either a path string or a URL name for reverse()
        kwargs: URL kwargs for reverse() (only used if use_reverse=True)
        use_reverse: If True, use reverse() with path_or_url_name as URL name
                    If False, use path_or_url_name as a direct path
        
    Returns:
        Absolute URL with correct protocol (https:// in production)
        
    Example:
        # Using reverse
        url = build_absolute_uri_https(request, 'quicklink-icon', {'pk': 1})
        
        # Using direct path
        url = build_absolute_uri_https(request, '/api/surveys/', use_reverse=False)
    """
    if not request:
        return None
    
    if use_reverse:
        path = reverse(path_or_url_name, kwargs=kwargs)
    else:
        path = path_or_url_name
    
    url = request.build_absolute_uri(path)
    return force_https(url, request)
