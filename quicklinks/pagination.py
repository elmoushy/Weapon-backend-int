"""
Custom pagination classes for the quicklinks app.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class QuickLinkPagination(PageNumberPagination):
    """
    Custom pagination for quick links with configurable page size.
    Default page_size is 20, can be customized via 'page_size' query parameter.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'status': 'success',
            'message': 'Quick links retrieved successfully',
            'data': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'results': data
            }
        })
