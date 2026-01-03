from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.core.cache import cache
from django.contrib.auth import get_user_model

from authenticate.models import User

class CachedJWTAuthentication(JWTAuthentication):
    CACHE_TIMEOUT = 60 * 15  # 15 minutes

    def get_user(self, validated_token):
        user_id = validated_token.get("user_id")

        if not user_id:
            raise AuthenticationFailed('Token contained no recognizable user identification')

        cache_key = f"user_jwt_{user_id}"
        user = cache.get(cache_key)

        if user is None:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise AuthenticationFailed("User not found")
            cache.set(cache_key, user, timeout=self.CACHE_TIMEOUT)

        return user
