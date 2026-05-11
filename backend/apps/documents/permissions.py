from __future__ import annotations

from django.contrib.auth.models import AbstractUser


def is_admin_user(user: AbstractUser) -> bool:
    return bool(user.is_superuser or user.groups.filter(name="Admin").exists())
