from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models.strategy import Strategy, StrategyVersion, StrategyParameter, StrategyTest, StrategyStatus as DBStrategyStatus
from app.schemas.strategy import (
    StrategyCreate, StrategyUpdate, StrategyResponse, StrategyListResponse,
    StrategyVersionCreate, StrategyVersionResponse, StrategyTestCreate, StrategyTestResponse
)
import hashlib
from datetime import datetime
import difflib

router = APIRouter()

def calculate_content_hash(code: str) -> str:
    """Calculate SHA-256 hash of strategy code"""
    return hashlib.sha256(code.encode()).hexdigest()

@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(strategy: StrategyCreate, db: Session = Depends(get_db)):
    """Create a new strategy with initial version"""
    # Check if strategy name already exists
    existing = db.query(Strategy).filter(Strategy.name == strategy.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Strategy with this name already exists")
    
    # Create strategy
    db_strategy = Strategy(
        name=strategy.name,
        description=strategy.description,
        status=DBStrategyStatus.DRAFT,
        created_by="system"  # TODO: Get from auth context
    )
    db.add(db_strategy)
    db.flush()
    
    # Create initial version
    content_hash = calculate_content_hash(strategy.code)
    db_version = StrategyVersion(
        strategy_id=db_strategy.id,
        version_number=1,
        code=strategy.code,
        config_schema=strategy.config_schema,
        commit_message=strategy.commit_message,
        content_hash=content_hash,
        created_by="system"
    )
    db.add(db_version)
    db.flush()
    
    # Set current version
    db_strategy.current_version_id = db_version.id
    
    # Create parameters
    if strategy.parameters:
        for param in strategy.parameters:
            db_param = StrategyParameter(
                strategy_id=db_strategy.id,
                name=param.name,
                param_type=param.param_type,
                default_value=param.default_value,
                description=param.description,
                min_value=param.min_value,
                max_value=param.max_value,
                allowed_values=param.allowed_values
            )
            db.add(db_param)
    
    db.commit()
    db.refresh(db_strategy)
    return db_strategy

@router.get("/", response_model=List[StrategyListResponse])
async def list_strategies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all strategies"""
    strategies = db.query(Strategy).offset(skip).limit(limit).all()
    return strategies

@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """Get strategy by ID"""
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy

@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(strategy_id: int, strategy_update: StrategyUpdate, db: Session = Depends(get_db)):
    """Update strategy metadata"""
    db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not db_strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    update_data = strategy_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_strategy, field, value)
    
    db.commit()
    db.refresh(db_strategy)
    return db_strategy

@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    """Delete strategy and all versions"""
    db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not db_strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    db.delete(db_strategy)
    db.commit()
    return None

# Version Management

@router.post("/{strategy_id}/versions", response_model=StrategyVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(strategy_id: int, version: StrategyVersionCreate, db: Session = Depends(get_db)):
    """Create a new version of the strategy"""
    db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not db_strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Get latest version number
    latest_version = db.query(StrategyVersion).filter(
        StrategyVersion.strategy_id == strategy_id
    ).order_by(StrategyVersion.version_number.desc()).first()
    
    next_version_number = (latest_version.version_number + 1) if latest_version else 1
    
    # Create new version
    content_hash = calculate_content_hash(version.code)
    db_version = StrategyVersion(
        strategy_id=strategy_id,
        version_number=next_version_number,
        code=version.code,
        config_schema=version.config_schema,
        commit_message=version.commit_message,
        content_hash=content_hash,
        created_by="system"
    )
    db.add(db_version)
    db.flush()
    
    # Update current version
    db_strategy.current_version_id = db_version.id
    
    db.commit()
    db.refresh(db_version)
    return db_version

@router.get("/{strategy_id}/versions", response_model=List[StrategyVersionResponse])
async def list_versions(strategy_id: int, db: Session = Depends(get_db)):
    """List all versions of a strategy"""
    versions = db.query(StrategyVersion).filter(
        StrategyVersion.strategy_id == strategy_id
    ).order_by(StrategyVersion.version_number.desc()).all()
    return versions

@router.get("/{strategy_id}/versions/{version_id}", response_model=StrategyVersionResponse)
async def get_version(strategy_id: int, version_id: int, db: Session = Depends(get_db)):
    """Get specific version"""
    version = db.query(StrategyVersion).filter(
        StrategyVersion.strategy_id == strategy_id,
        StrategyVersion.id == version_id
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version

@router.get("/{strategy_id}/versions/{version_id}/diff")
async def get_version_diff(strategy_id: int, version_id: int, compare_to: int, db: Session = Depends(get_db)):
    """Get diff between two versions"""
    version1 = db.query(StrategyVersion).filter(
        StrategyVersion.strategy_id == strategy_id,
        StrategyVersion.id == version_id
    ).first()
    version2 = db.query(StrategyVersion).filter(
        StrategyVersion.strategy_id == strategy_id,
        StrategyVersion.id == compare_to
    ).first()
    
    if not version1 or not version2:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Generate unified diff
    diff = list(difflib.unified_diff(
        version2.code.splitlines(keepends=True),
        version1.code.splitlines(keepends=True),
        fromfile=f"Version {version2.version_number}",
        tofile=f"Version {version1.version_number}",
        lineterm=''
    ))
    
    return {
        "from_version": version2.version_number,
        "to_version": version1.version_number,
        "diff": ''.join(diff)
    }

# Testing

@router.post("/{strategy_id}/tests", response_model=StrategyTestResponse, status_code=status.HTTP_201_CREATED)
async def create_test(strategy_id: int, test: StrategyTestCreate, db: Session = Depends(get_db)):
    """Create and run a test for the strategy"""
    db_strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not db_strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Create test record
    db_test = StrategyTest(
        strategy_id=strategy_id,
        version_id=db_strategy.current_version_id,
        test_type=test.test_type,
        status="running",
        started_at=datetime.now()
    )
    db.add(db_test)
    db.commit()
    db.refresh(db_test)
    
    # TODO: Trigger async test execution (Celery task)
    # For now, just return the test record
    
    return db_test

@router.get("/{strategy_id}/tests", response_model=List[StrategyTestResponse])
async def list_tests(strategy_id: int, db: Session = Depends(get_db)):
    """List all tests for a strategy"""
    tests = db.query(StrategyTest).filter(
        StrategyTest.strategy_id == strategy_id
    ).order_by(StrategyTest.started_at.desc()).all()
    return tests

@router.get("/{strategy_id}/tests/{test_id}", response_model=StrategyTestResponse)
async def get_test(strategy_id: int, test_id: int, db: Session = Depends(get_db)):
    """Get test results"""
    test = db.query(StrategyTest).filter(
        StrategyTest.strategy_id == strategy_id,
        StrategyTest.id == test_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return test
