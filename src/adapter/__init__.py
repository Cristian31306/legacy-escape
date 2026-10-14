"""Adapter package."""
from .legacy_adapter import (
    check_legacy_health,
    resolve_schema,
    get_member,
    get_beneficiaries,
    get_company,
    retire_member,
)

__all__ = [
    "check_legacy_health",
    "resolve_schema",
    "get_member",
    "get_beneficiaries",
    "get_company",
    "retire_member",
]
