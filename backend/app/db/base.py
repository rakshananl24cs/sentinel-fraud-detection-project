"""SQLAlchemy 2.0 Declarative Base definition.

Provides the shared DeclarativeBase class for all application ORM models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 ORM models in the system."""
    pass
