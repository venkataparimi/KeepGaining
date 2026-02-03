"""
Pydantic Schemas - Instrument & Master Data
KeepGaining Trading Platform

API schemas for:
- Instruments
- Equities
- Futures
- Options
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Base Schemas
# =============================================================================

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# =============================================================================
# Instrument Schemas
# =============================================================================

class InstrumentBase(BaseSchema):
    """Base instrument fields."""
    trading_symbol: str = Field(..., max_length=50)
    exchange: str = Field(..., max_length=10)
    segment: str = Field(..., max_length=20)
    instrument_type: str = Field(..., max_length=20)
    underlying: Optional[str] = Field(None, max_length=50)
    isin: Optional[str] = Field(None, max_length=12)
    lot_size: int = Field(default=1, ge=1)
    tick_size: Decimal = Field(default=Decimal("0.05"))
    is_active: bool = True


class InstrumentCreate(InstrumentBase):
    """Schema for creating an instrument."""
    pass


class InstrumentUpdate(BaseSchema):
    """Schema for updating an instrument."""
    trading_symbol: Optional[str] = Field(None, max_length=50)
    lot_size: Optional[int] = Field(None, ge=1)
    tick_size: Optional[Decimal] = None
    is_active: Optional[bool] = None


class InstrumentResponse(InstrumentBase, TimestampMixin):
    """Schema for instrument response."""
    instrument_id: UUID


class InstrumentDetail(InstrumentResponse):
    """Detailed instrument response with related data."""
    equity: Optional["EquityResponse"] = None
    broker_mappings: List["BrokerSymbolMappingResponse"] = []


# =============================================================================
# Equity Schemas
# =============================================================================

class EquityBase(BaseSchema):
    """Base equity fields."""
    company_name: str = Field(..., max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    sector: Optional[str] = Field(None, max_length=100)
    face_value: Optional[Decimal] = None
    is_fno: bool = False
    fno_lot_size: Optional[int] = None
    market_cap_category: Optional[str] = Field(None, max_length=20)
    listing_date: Optional[date] = None
    is_index_constituent: bool = False


class EquityCreate(EquityBase):
    """Schema for creating equity."""
    instrument_id: UUID


class EquityUpdate(BaseSchema):
    """Schema for updating equity."""
    company_name: Optional[str] = Field(None, max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    sector: Optional[str] = Field(None, max_length=100)
    is_fno: Optional[bool] = None
    fno_lot_size: Optional[int] = None
    market_cap_category: Optional[str] = None
    is_index_constituent: Optional[bool] = None


class EquityResponse(EquityBase, TimestampMixin):
    """Schema for equity response."""
    equity_id: UUID
    instrument_id: UUID


# =============================================================================
# Future Schemas
# =============================================================================

class FutureBase(BaseSchema):
    """Base future fields."""
    expiry_date: date
    lot_size: int = Field(..., ge=1)
    contract_type: Optional[str] = Field(None, max_length=10)


class FutureCreate(FutureBase):
    """Schema for creating future."""
    instrument_id: UUID
    underlying_instrument_id: Optional[UUID] = None


class FutureResponse(FutureBase):
    """Schema for future response."""
    future_id: UUID
    instrument_id: UUID
    underlying_instrument_id: Optional[UUID] = None
    created_at: Optional[datetime] = None


# =============================================================================
# Option Schemas
# =============================================================================

class OptionBase(BaseSchema):
    """Base option fields."""
    strike_price: Decimal
    option_type: str = Field(..., max_length=2)  # CE, PE
    expiry_date: date
    expiry_type: Optional[str] = Field(None, max_length=10)  # WEEKLY, MONTHLY
    lot_size: int = Field(..., ge=1)


class OptionCreate(OptionBase):
    """Schema for creating option."""
    instrument_id: UUID
    underlying_instrument_id: Optional[UUID] = None


class OptionResponse(OptionBase):
    """Schema for option response."""
    option_id: UUID
    instrument_id: UUID
    underlying_instrument_id: Optional[UUID] = None
    created_at: Optional[datetime] = None


class OptionChainItem(BaseSchema):
    """Single item in option chain."""
    strike_price: Decimal
    ce_ltp: Optional[Decimal] = None
    ce_oi: Optional[int] = None
    ce_volume: Optional[int] = None
    ce_iv: Optional[Decimal] = None
    ce_delta: Optional[Decimal] = None
    pe_ltp: Optional[Decimal] = None
    pe_oi: Optional[int] = None
    pe_volume: Optional[int] = None
    pe_iv: Optional[Decimal] = None
    pe_delta: Optional[Decimal] = None


class OptionChainResponse(BaseSchema):
    """Full option chain response."""
    underlying: str
    underlying_price: Decimal
    expiry_date: date
    timestamp: datetime
    atm_strike: Decimal
    pcr_oi: Optional[Decimal] = None
    pcr_volume: Optional[Decimal] = None
    max_pain: Optional[Decimal] = None
    chain: List[OptionChainItem]


# =============================================================================
# Broker Symbol Mapping Schemas
# =============================================================================

class BrokerSymbolMappingBase(BaseSchema):
    """Base broker mapping fields."""
    broker_name: str = Field(..., max_length=20)
    broker_symbol: str = Field(..., max_length=100)
    broker_token: Optional[str] = Field(None, max_length=50)
    exchange_code: Optional[str] = Field(None, max_length=10)
    is_active: bool = True


class BrokerSymbolMappingCreate(BrokerSymbolMappingBase):
    """Schema for creating broker mapping."""
    instrument_id: UUID


class BrokerSymbolMappingResponse(BrokerSymbolMappingBase, TimestampMixin):
    """Schema for broker mapping response."""
    mapping_id: UUID
    instrument_id: UUID


# =============================================================================
# Sector Schemas
# =============================================================================

class SectorBase(BaseSchema):
    """Base sector fields."""
    sector_name: str = Field(..., max_length=100)
    sector_code: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = None
    is_active: bool = True


class SectorCreate(SectorBase):
    """Schema for creating sector."""
    parent_sector_id: Optional[UUID] = None


class SectorResponse(SectorBase):
    """Schema for sector response."""
    sector_id: UUID
    parent_sector_id: Optional[UUID] = None
    created_at: Optional[datetime] = None


# =============================================================================
# Index Constituent Schemas
# =============================================================================

class IndexConstituentBase(BaseSchema):
    """Base index constituent fields."""
    weight: Optional[Decimal] = None
    effective_date: date
    end_date: Optional[date] = None


class IndexConstituentCreate(IndexConstituentBase):
    """Schema for creating constituent."""
    index_instrument_id: UUID
    constituent_instrument_id: UUID


class IndexConstituentResponse(IndexConstituentBase):
    """Schema for constituent response."""
    id: UUID
    index_instrument_id: UUID
    constituent_instrument_id: UUID
    created_at: Optional[datetime] = None


# Forward references
InstrumentDetail.model_rebuild()
