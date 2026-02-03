from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON, Enum as SQLEnum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import enum

class DeploymentStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class DeploymentType(str, enum.Enum):
    FULL = "full"
    CANARY = "canary"
    SANDBOX = "sandbox"

class Deployment(Base):
    """Strategy deployment record"""
    __tablename__ = "deployments"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategy_templates.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("strategy_template_versions.id"), nullable=False)
    
    # Deployment configuration
    deployment_type = Column(SQLEnum(DeploymentType), default=DeploymentType.SANDBOX, nullable=False)
    status = Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING_APPROVAL, nullable=False)
    
    # Canary configuration
    canary_percent = Column(Float, default=0.0)  # 0-100, percentage of traffic
    
    # Deployment metadata
    requested_by = Column(String(255))
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    deployed_at = Column(DateTime(timezone=True))
    
    # Approval tracking
    approved_by = Column(String(255))
    approved_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)
    
    # Deployment results
    deployment_log = Column(JSON)  # Logs from deployment process
    error_message = Column(Text)
    
    # Relationships
    approvals = relationship("DeploymentApproval", back_populates="deployment", cascade="all, delete-orphan")

class DeploymentApproval(Base):
    """Approval requests for deployments"""
    __tablename__ = "deployment_approvals"
    
    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False)
    
    # Approval details
    approver = Column(String(255), nullable=False)
    approved = Column(Boolean, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    deployment = relationship("Deployment", back_populates="approvals")

class DeploymentHistory(Base):
    """Historical record of all deployment events"""
    __tablename__ = "deployment_history"
    
    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False)
    
    # Event details
    event_type = Column(String(50), nullable=False)  # status_change, canary_update, rollback
    from_status = Column(String(50))
    to_status = Column(String(50))
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(255))
