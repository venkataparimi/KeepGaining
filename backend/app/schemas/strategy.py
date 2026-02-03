from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class StrategyStatus(str, Enum):
    DRAFT = "draft"
    TESTING = "testing"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"

class StrategyParameterSchema(BaseModel):
    name: str
    param_type: str  # int, float, string, bool
    default_value: Any
    description: Optional[str] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    allowed_values: Optional[List[Any]] = None

class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    code: str = Field(..., min_length=1)
    config_schema: Optional[Dict[str, Any]] = None
    parameters: Optional[List[StrategyParameterSchema]] = []
    commit_message: Optional[str] = "Initial version"

class StrategyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[StrategyStatus] = None

class StrategyVersionCreate(BaseModel):
    code: str = Field(..., min_length=1)
    config_schema: Optional[Dict[str, Any]] = None
    commit_message: str = Field(..., min_length=1)

class StrategyVersionResponse(BaseModel):
    id: int
    version_number: int
    code: str
    config_schema: Optional[Dict[str, Any]]
    commit_message: Optional[str]
    created_at: datetime
    created_by: Optional[str]
    content_hash: str
    
    class Config:
        from_attributes = True

class StrategyResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: StrategyStatus
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[str]
    current_version_id: Optional[int]
    current_version: Optional[StrategyVersionResponse]
    
    class Config:
        from_attributes = True

class StrategyListResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: StrategyStatus
    created_at: datetime
    current_version_id: Optional[int]
    
    class Config:
        from_attributes = True

class StrategyTestCreate(BaseModel):
    test_type: str  # unit, backtest, walk_forward
    config: Optional[Dict[str, Any]] = {}

class StrategyTestResponse(BaseModel):
    id: int
    strategy_id: int
    version_id: Optional[int]
    test_type: str
    status: str
    results: Optional[Dict[str, Any]]
    metrics: Optional[Dict[str, Any]]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    
    class Config:
        from_attributes = True
