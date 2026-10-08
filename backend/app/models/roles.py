"""Canonical application roles."""

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    CLINICIAN = "clinician"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    OPERATOR = "operator"
