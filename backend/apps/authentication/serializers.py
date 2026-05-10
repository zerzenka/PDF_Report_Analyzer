from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken


def user_role(user) -> str:
    """
    Map Django users to API roles used by the SPA.

    - `admin`: superusers or members of the "Admin" group (case-insensitive).
    - `reviewer`: everyone else (including members of the "Reviewer" group).
    """
    if user.is_superuser:
        return "admin"
    if user.groups.filter(name__iexact="Admin").exists():
        return "admin"
    return "reviewer"


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds `role` as a JWT claim and as a top-level field on the response."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user_role(user)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["role"] = user_role(self.user)
        return data


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """Ensures refreshed access tokens include an up-to-date `role` claim."""

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])

        user_id = refresh.payload.get(jwt_settings.USER_ID_CLAIM, None)
        user = None
        if user_id:
            user = get_user_model().objects.get(
                **{jwt_settings.USER_ID_FIELD: user_id}
            )
            if not jwt_settings.USER_AUTHENTICATION_RULE(user):
                raise AuthenticationFailed(
                    self.error_messages["no_active_account"],
                    "no_active_account",
                )

        access = refresh.access_token
        if user is not None:
            access["role"] = user_role(user)

        data = {"access": str(access)}

        if jwt_settings.ROTATE_REFRESH_TOKENS:
            if jwt_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    refresh.blacklist()
                except AttributeError:
                    pass

            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            refresh.outstand()

            data["refresh"] = str(refresh)

        if user is not None:
            data["role"] = user_role(user)

        return data
