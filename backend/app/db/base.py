"""
SQLAlchemy Base Model Configuration
KeepGaining Trading Platform
"""

from typing import Any
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, declared_attr


# Naming convention for constraints (helps with migrations)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    
    Features:
    - Automatic table name generation from class name
    - Proper metadata with naming conventions
    - Type hints support
    """
    
    metadata = metadata
    
    # Common fields can be defined here
    __name__: str
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name automatically from class name."""
        # Convert CamelCase to snake_case
        name = cls.__name__
        result = [name[0].lower()]
        for char in name[1:]:
            if char.isupper():
                result.extend(['_', char.lower()])
            else:
                result.append(char)
        return ''.join(result)
