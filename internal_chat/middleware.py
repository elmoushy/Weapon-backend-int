"""
WebSocket Authentication Middleware for Internal Chat
"""
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import jwt
from django.conf import settings

User = get_user_model()


class TokenAuthMiddleware(BaseMiddleware):
    """
    Authenticates WebSocket connections using JWT token from query string.
    Usage: ws://yourapp.com/ws/internal-chat/threads/{thread_id}/?token=<jwt>
    """
    
    async def __call__(self, scope, receive, send):
        # Extract token from query string: ?token=<jwt>
        query_string = scope.get('query_string', b'').decode()
        token = None
        
        for param in query_string.split('&'):
            if param.startswith('token='):
                token = param.split('=', 1)[1]
                break
        
        if token:
            try:
                # Validate JWT token
                UntypedToken(token)
                
                # Decode token to get user_id
                decoded_data = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=["HS256"]
                )
                user_id = decoded_data.get('user_id')
                
                # Get user from database
                scope['user'] = await self.get_user(user_id)
            except (InvalidToken, TokenError, KeyError, jwt.DecodeError) as e:
                # Invalid token, set anonymous user
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)
    
    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return AnonymousUser()
