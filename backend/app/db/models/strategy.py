from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum

class StrategyStatus(str, enum.Enum):
    DRAFT = "draft"
    TESTING = "testing"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"

class StrategyTemplate(Base):
    """Strategy template with version control (renamed to avoid conflict)"""
    __tablename__ = "strategy_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text)
    status = Column(SQLEnum(StrategyStatus), default=StrategyStatus.DRAFT, nullable=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(255))
    
    # Current active version
    current_version_id = Column(Integer, ForeignKey("strategy_template_versions.id"))
    
    # Relationships
    versions = relationship("StrategyTemplateVersion", back_populates="strategy", foreign_keys="StrategyTemplateVersion.strategy_id")
    current_version = relationship("StrategyTemplateVersion", foreign_keys=[current_version_id], post_update=True)
    parameters = relationship("StrategyTemplateParameter", back_populates="strategy", cascade="all, delete-orphan")
    tests = relationship("StrategyTemplateTest", back_populates="strategy", cascade="all, delete-orphan")

# Alias for backward compatibility
Strategy = StrategyTemplate

class StrategyTemplateVersion(Base):
    """Version control for strategy templates"""
    __tablename__ = "strategy_template_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategy_templates.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    
    # Code and configuration
    code = Column(Text, nullable=False)
    config_schema = Column(JSON)
    
    # Version metadata
    commit_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(255))
    content_hash = Column(String(64), index=True)
    
    # Relationships
    strategy = relationship("StrategyTemplate", back_populates="versions", foreign_keys=[strategy_id])
    
    __table_args__ = ({'sqlite_autoincrement': True},)

# Alias for backward compatibility
StrategyVersion = StrategyTemplateVersion

class StrategyTemplateParameter(Base):
    """Strategy configuration parameters"""
    __tablename__ = "strategy_template_parameters"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategy_templates.id"), nullable=False)
    
    name = Column(String(255), nullable=False)
    param_type = Column(String(50), nullable=False)
    default_value = Column(JSON)
    description = Column(Text)
    
    min_value = Column(JSON)
    max_value = Column(JSON)
    allowed_values = Column(JSON)
    
    strategy = relationship("StrategyTemplate", back_populates="parameters")

# Alias for backward compatibility
StrategyParameter = StrategyTemplateParameter

class StrategyTemplateTest(Base):
    """Test results for strategy templates"""
    __tablename__ = "strategy_template_tests"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategy_templates.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("strategy_template_versions.id"))
    
    test_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    
    results = Column(JSON)
    metrics = Column(JSON)
    
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    
    strategy = relationship("StrategyTemplate", back_populates="tests")

# Alias for backward compatibility
StrategyTest = StrategyTemplateTest
