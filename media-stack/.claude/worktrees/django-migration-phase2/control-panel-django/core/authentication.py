from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.models import ApiKey, User
from core.security import hash_api_key


class AnonymousServiceUser:
    """Stands in for `request.user` when a valid X-Api-Key header authenticated
    the request instead of a session — mirrors the FastAPI-era
    current_user_or_service dependency returning None for a service caller,
    adapted to DRF's requirement that request.user be truthy."""

    is_authenticated = True
    is_service_account = True
    id = None


class SessionOrApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.META.get("HTTP_X_API_KEY")
        if api_key:
            key_hash = hash_api_key(api_key)
            try:
                key_row = ApiKey.objects.get(key_hash=key_hash)
            except ApiKey.DoesNotExist:
                raise AuthenticationFailed("Invalid API key")
            key_row.last_used_at = timezone.now()
            key_row.save(update_fields=["last_used_at"])
            return (AnonymousServiceUser(), None)

        user_id = request.session.get("user_id")
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return None
            return (user, None)

        return None
