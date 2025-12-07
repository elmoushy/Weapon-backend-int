from django.utils.deprecation import MiddlewareMixin

class ApiCsrfExemptMiddleware(MiddlewareMixin):
    """
    Middleware to exempt API endpoints from CSRF checks.
    This is safe because API endpoints are protected by JWT authentication.
    """
    def process_request(self, request):
        if request.path.startswith('/api/'):
            # print(f"Exempting CSRF for: {request.path}")
            setattr(request, '_dont_enforce_csrf_checks', True)
