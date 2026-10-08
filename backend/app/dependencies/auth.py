"""Compatibility exports for the authenticated database user dependency."""

from app.models import User, UserRole
from app.security.auth import get_current_user


# Existing routers use this annotation. The dependency now returns the actual
# SQLAlchemy user row rather than a synthetic context.
UserContext = User
