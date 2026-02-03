"""
Base Repository Pattern Implementation
KeepGaining Trading Platform

Provides generic CRUD operations with:
- Type-safe async repository base class
- Pagination, filtering, and sorting
- Soft delete support
- Transaction management
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import (
    Any, Dict, Generic, List, Optional, Sequence,
    Type, TypeVar, Union
)
from uuid import UUID

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.db.base import Base


# Type variables
ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = 1
    page_size: int = 50
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class SortParams(BaseModel):
    """Sorting parameters."""
    sort_by: str = "created_at"
    sort_order: str = "desc"  # asc or desc


class PaginatedResponse(BaseModel, Generic[ModelType]):
    """Paginated response wrapper."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType], ABC):
    """
    Generic async repository with CRUD operations.
    
    Type Parameters:
        ModelType: SQLAlchemy model class
        CreateSchemaType: Pydantic schema for creation
        UpdateSchemaType: Pydantic schema for updates
    """
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.
        
        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session
    
    # =========================================================================
    # Basic CRUD Operations
    # =========================================================================
    
    async def get(self, id: Union[UUID, int, str]) -> Optional[ModelType]:
        """
        Get a single record by ID.
        
        Args:
            id: Primary key value
            
        Returns:
            Model instance or None
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_field(
        self,
        field_name: str,
        value: Any,
    ) -> Optional[ModelType]:
        """
        Get a single record by field value.
        
        Args:
            field_name: Field/column name
            value: Value to match
            
        Returns:
            Model instance or None
        """
        field = getattr(self.model, field_name, None)
        if field is None:
            raise ValueError(f"Field {field_name} not found on {self.model.__name__}")
        
        result = await self.session.execute(
            select(self.model).where(field == value)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ModelType]:
        """
        Get multiple records with optional filtering.
        
        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            filters: Dict of field_name -> value for filtering
            
        Returns:
            List of model instances
        """
        query = select(self.model)
        
        if filters:
            conditions = []
            for field_name, value in filters.items():
                field = getattr(self.model, field_name, None)
                if field is not None:
                    conditions.append(field == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_paginated(
        self,
        pagination: PaginationParams,
        sort: Optional[SortParams] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PaginatedResponse[ModelType]:
        """
        Get paginated records with sorting.
        
        Args:
            pagination: Pagination parameters
            sort: Sorting parameters
            filters: Filtering conditions
            
        Returns:
            Paginated response with items and metadata
        """
        # Build base query
        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)
        
        # Apply filters
        if filters:
            conditions = []
            for field_name, value in filters.items():
                field = getattr(self.model, field_name, None)
                if field is not None:
                    conditions.append(field == value)
            if conditions:
                filter_clause = and_(*conditions)
                query = query.where(filter_clause)
                count_query = count_query.where(filter_clause)
        
        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply sorting
        if sort:
            sort_field = getattr(self.model, sort.sort_by, None)
            if sort_field is not None:
                if sort.sort_order.lower() == "desc":
                    query = query.order_by(sort_field.desc())
                else:
                    query = query.order_by(sort_field.asc())
        
        # Apply pagination
        query = query.offset(pagination.offset).limit(pagination.page_size)
        
        # Execute query
        result = await self.session.execute(query)
        items = list(result.scalars().all())
        
        # Calculate pagination metadata
        total_pages = (total + pagination.page_size - 1) // pagination.page_size
        
        return PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            has_next=pagination.page < total_pages,
            has_prev=pagination.page > 1,
        )
    
    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        """
        Create a new record.
        
        Args:
            obj_in: Creation schema with data
            
        Returns:
            Created model instance
        """
        obj_data = obj_in.model_dump()
        db_obj = self.model(**obj_data)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj
    
    async def create_many(self, objs_in: List[CreateSchemaType]) -> List[ModelType]:
        """
        Create multiple records.
        
        Args:
            objs_in: List of creation schemas
            
        Returns:
            List of created model instances
        """
        db_objs = []
        for obj_in in objs_in:
            obj_data = obj_in.model_dump()
            db_obj = self.model(**obj_data)
            self.session.add(db_obj)
            db_objs.append(db_obj)
        
        await self.session.commit()
        
        for db_obj in db_objs:
            await self.session.refresh(db_obj)
        
        return db_objs
    
    async def update(
        self,
        id: Union[UUID, int, str],
        obj_in: Union[UpdateSchemaType, Dict[str, Any]],
    ) -> Optional[ModelType]:
        """
        Update a record by ID.
        
        Args:
            id: Primary key value
            obj_in: Update schema or dict with new values
            
        Returns:
            Updated model instance or None
        """
        db_obj = await self.get(id)
        if not db_obj:
            return None
        
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        # Update timestamp if exists
        if hasattr(db_obj, "updated_at"):
            setattr(db_obj, "updated_at", datetime.now(timezone.utc))
        
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj
    
    async def delete(self, id: Union[UUID, int, str]) -> bool:
        """
        Delete a record by ID (hard delete).
        
        Args:
            id: Primary key value
            
        Returns:
            True if deleted, False if not found
        """
        db_obj = await self.get(id)
        if not db_obj:
            return False
        
        await self.session.delete(db_obj)
        await self.session.commit()
        return True
    
    async def soft_delete(self, id: Union[UUID, int, str]) -> Optional[ModelType]:
        """
        Soft delete a record by setting is_active=False.
        
        Args:
            id: Primary key value
            
        Returns:
            Updated model instance or None
        """
        return await self.update(id, {"is_active": False})
    
    # =========================================================================
    # Advanced Query Methods
    # =========================================================================
    
    async def exists(self, id: Union[UUID, int, str]) -> bool:
        """Check if a record exists by ID."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.model.id == id)
        )
        return (result.scalar() or 0) > 0
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with optional filtering."""
        query = select(func.count()).select_from(self.model)
        
        if filters:
            conditions = []
            for field_name, value in filters.items():
                field = getattr(self.model, field_name, None)
                if field is not None:
                    conditions.append(field == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def get_by_ids(self, ids: List[Union[UUID, int, str]]) -> List[ModelType]:
        """Get multiple records by IDs."""
        result = await self.session.execute(
            select(self.model).where(self.model.id.in_(ids))
        )
        return list(result.scalars().all())
    
    async def upsert(
        self,
        obj_in: CreateSchemaType,
        unique_fields: List[str],
    ) -> ModelType:
        """
        Insert or update based on unique fields.
        
        Args:
            obj_in: Creation schema with data
            unique_fields: Fields to check for existence
            
        Returns:
            Created or updated model instance
        """
        obj_data = obj_in.model_dump()
        
        # Build filter for unique fields
        filters = {field: obj_data[field] for field in unique_fields if field in obj_data}
        
        # Check if exists
        existing = await self.get_all(filters=filters, limit=1)
        
        if existing:
            # Update existing
            return await self.update(existing[0].id, obj_in)
        else:
            # Create new
            return await self.create(obj_in)


class ReadOnlyRepository(Generic[ModelType], ABC):
    """
    Read-only repository for reference data.
    
    Use for tables that should not be modified through the application.
    """
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
    
    async def get(self, id: Union[UUID, int, str]) -> Optional[ModelType]:
        """Get a single record by ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ModelType]:
        """Get multiple records with optional filtering."""
        query = select(self.model)
        
        if filters:
            conditions = []
            for field_name, value in filters.items():
                field = getattr(self.model, field_name, None)
                if field is not None:
                    conditions.append(field == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class TimeSeriesRepository(Generic[ModelType, CreateSchemaType], ABC):
    """
    Repository for time-series data with optimized queries.
    
    Optimized for:
    - Range queries by timestamp
    - Aggregations
    - Latest value queries
    """
    
    def __init__(
        self,
        model: Type[ModelType],
        session: AsyncSession,
        timestamp_field: str = "timestamp",
    ):
        self.model = model
        self.session = session
        self.timestamp_field = timestamp_field
    
    @property
    def _timestamp_col(self):
        """Get the timestamp column."""
        return getattr(self.model, self.timestamp_field)
    
    async def get_range(
        self,
        start: datetime,
        end: datetime,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[ModelType]:
        """
        Get records within a time range.
        
        Args:
            start: Start timestamp (inclusive)
            end: End timestamp (inclusive)
            filters: Additional filters
            limit: Maximum records
            
        Returns:
            List of records ordered by timestamp
        """
        query = select(self.model).where(
            and_(
                self._timestamp_col >= start,
                self._timestamp_col <= end,
            )
        )
        
        if filters:
            conditions = []
            for field_name, value in filters.items():
                field = getattr(self.model, field_name, None)
                if field is not None:
                    conditions.append(field == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        query = query.order_by(self._timestamp_col.asc())
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_latest(
        self,
        filters: Optional[Dict[str, Any]] = None,
        count: int = 1,
    ) -> List[ModelType]:
        """
        Get the latest records.
        
        Args:
            filters: Filtering conditions
            count: Number of records to return
            
        Returns:
            Latest records (most recent first)
        """
        query = select(self.model)
        
        if filters:
            conditions = []
            for field_name, value in filters.items():
                field = getattr(self.model, field_name, None)
                if field is not None:
                    conditions.append(field == value)
            if conditions:
                query = query.where(and_(*conditions))
        
        query = query.order_by(self._timestamp_col.desc()).limit(count)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def insert(self, obj_in: CreateSchemaType) -> ModelType:
        """Insert a time-series record."""
        obj_data = obj_in.model_dump()
        db_obj = self.model(**obj_data)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj
    
    async def insert_many(self, objs_in: List[CreateSchemaType]) -> int:
        """
        Bulk insert time-series records.
        
        Returns:
            Number of records inserted
        """
        db_objs = [self.model(**obj.model_dump()) for obj in objs_in]
        self.session.add_all(db_objs)
        await self.session.commit()
        return len(db_objs)
    
    async def delete_before(self, before: datetime) -> int:
        """
        Delete records before a timestamp.
        
        Args:
            before: Delete records before this timestamp
            
        Returns:
            Number of records deleted
        """
        result = await self.session.execute(
            delete(self.model).where(self._timestamp_col < before)
        )
        await self.session.commit()
        return result.rowcount


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "BaseRepository",
    "ReadOnlyRepository",
    "TimeSeriesRepository",
    "PaginationParams",
    "SortParams",
    "PaginatedResponse",
]
