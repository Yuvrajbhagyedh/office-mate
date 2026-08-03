"""Shared singletons wired from configuration."""
from __future__ import annotations

from .config import settings
from .storage.registry import Registry
from .storage.users import UserStore

registry = Registry(settings.registry_db)
user_store = UserStore(settings.registry_db)
