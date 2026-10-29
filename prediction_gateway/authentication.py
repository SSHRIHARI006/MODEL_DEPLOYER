import hashlib
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from api_keys.models import UniversalAPIKey

class UniversalOrJWTAuthentication(BaseAuthentication):
    """
    Tries to authenticate using a Universal API Key first.
    If the token doesn't match the universal key format, it falls back to JWT.
    """
    def authenticate(self, request):
        token = request.headers.get("X-API-Key")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return None

        # Check if it looks like a Universal API Key
        if token.startswith("md_live_"):
            try:
                prefix = token[:12]
            except IndexError:
                raise AuthenticationFailed("Malformed API Key")
            
            hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()
            
            try:
                key_obj = UniversalAPIKey.objects.get(
                    prefix=prefix,
                    hashed_key=hashed_token,
                    is_active=True
                )
            except UniversalAPIKey.DoesNotExist:
                raise AuthenticationFailed("Invalid or inactive API Key")

            # CODE-01: Record last_used_at when universal key is used
            key_obj.last_used_at = timezone.now()
            key_obj.save(update_fields=['last_used_at'])

            # Return the user and the token (DRF standard)
            return (key_obj.user, token)
        
        # Fallback to standard JWT for UI Playground requests
        jwt_auth = JWTAuthentication()
        try:
            return jwt_auth.authenticate(request)
        except InvalidToken:
            return None
