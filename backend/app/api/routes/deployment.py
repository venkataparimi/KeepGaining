from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models.deployment import Deployment, DeploymentApproval, DeploymentHistory, DeploymentStatus, DeploymentType
from app.db.models.strategy import Strategy
from datetime import datetime

router = APIRouter()

class DeploymentRequest(BaseModel):
    strategy_id: int
    version_id: int
    deployment_type: DeploymentType = DeploymentType.SANDBOX
    canary_percent: Optional[float] = 0.0

class ApprovalRequest(BaseModel):
    approved: bool
    comment: Optional[str] = None

class CanaryUpdateRequest(BaseModel):
    canary_percent: float

@router.post("/deployments")
async def create_deployment(
    request: DeploymentRequest,
    db: Session = Depends(get_db)
):
    """Create a new deployment request"""
    # Verify strategy and version exist
    strategy = db.query(Strategy).filter(Strategy.id == request.strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Create deployment
    deployment = Deployment(
        strategy_id=request.strategy_id,
        version_id=request.version_id,
        deployment_type=request.deployment_type,
        status=DeploymentStatus.PENDING_APPROVAL,
        canary_percent=request.canary_percent if request.deployment_type == DeploymentType.CANARY else 0.0,
        requested_by="system"  # TODO: Get from auth context
    )
    db.add(deployment)
    db.flush()
    
    # Create history entry
    history = DeploymentHistory(
        deployment_id=deployment.id,
        event_type="created",
        to_status=DeploymentStatus.PENDING_APPROVAL.value,
        details={"deployment_type": request.deployment_type.value},
        created_by="system"
    )
    db.add(history)
    
    db.commit()
    db.refresh(deployment)
    
    return {
        "id": deployment.id,
        "status": deployment.status,
        "deployment_type": deployment.deployment_type,
        "requested_at": deployment.requested_at
    }

@router.get("/deployments")
async def list_deployments(
    status: Optional[DeploymentStatus] = None,
    db: Session = Depends(get_db)
):
    """List all deployments"""
    query = db.query(Deployment)
    if status:
        query = query.filter(Deployment.status == status)
    
    deployments = query.order_by(Deployment.requested_at.desc()).all()
    return deployments

@router.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: int, db: Session = Depends(get_db)):
    """Get deployment details"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment

@router.post("/deployments/{deployment_id}/approve")
async def approve_deployment(
    deployment_id: int,
    approval: ApprovalRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Approve or reject a deployment"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    if deployment.status != DeploymentStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Deployment is not pending approval")
    
    # Create approval record
    approval_record = DeploymentApproval(
        deployment_id=deployment_id,
        approver="system",  # TODO: Get from auth context
        approved=approval.approved,
        comment=approval.comment
    )
    db.add(approval_record)
    
    # Update deployment status
    if approval.approved:
        deployment.status = DeploymentStatus.APPROVED
        deployment.approved_by = "system"
        deployment.approved_at = datetime.now()
        
        # Trigger deployment in background
        background_tasks.add_task(execute_deployment, deployment_id, db)
    else:
        deployment.status = DeploymentStatus.REJECTED
        deployment.rejection_reason = approval.comment
    
    # Create history entry
    history = DeploymentHistory(
        deployment_id=deployment_id,
        event_type="approval_decision",
        from_status=DeploymentStatus.PENDING_APPROVAL.value,
        to_status=deployment.status.value,
        details={"approved": approval.approved, "comment": approval.comment},
        created_by="system"
    )
    db.add(history)
    
    db.commit()
    db.refresh(deployment)
    
    return deployment

@router.post("/deployments/{deployment_id}/canary")
async def update_canary(
    deployment_id: int,
    update: CanaryUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update canary rollout percentage"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    if deployment.deployment_type != DeploymentType.CANARY:
        raise HTTPException(status_code=400, detail="Not a canary deployment")
    
    if deployment.status != DeploymentStatus.DEPLOYED:
        raise HTTPException(status_code=400, detail="Deployment is not active")
    
    old_percent = deployment.canary_percent
    deployment.canary_percent = max(0.0, min(100.0, update.canary_percent))
    
    # Create history entry
    history = DeploymentHistory(
        deployment_id=deployment_id,
        event_type="canary_update",
        details={
            "from_percent": old_percent,
            "to_percent": deployment.canary_percent
        },
        created_by="system"
    )
    db.add(history)
    
    db.commit()
    db.refresh(deployment)
    
    return deployment

@router.post("/deployments/{deployment_id}/rollback")
async def rollback_deployment(deployment_id: int, db: Session = Depends(get_db)):
    """Rollback a deployment"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    if deployment.status != DeploymentStatus.DEPLOYED:
        raise HTTPException(status_code=400, detail="Deployment is not active")
    
    old_status = deployment.status
    deployment.status = DeploymentStatus.ROLLED_BACK
    
    # Create history entry
    history = DeploymentHistory(
        deployment_id=deployment_id,
        event_type="rollback",
        from_status=old_status.value,
        to_status=DeploymentStatus.ROLLED_BACK.value,
        created_by="system"
    )
    db.add(history)
    
    db.commit()
    db.refresh(deployment)
    
    return deployment

@router.get("/deployments/{deployment_id}/history")
async def get_deployment_history(deployment_id: int, db: Session = Depends(get_db)):
    """Get deployment history"""
    history = db.query(DeploymentHistory).filter(
        DeploymentHistory.deployment_id == deployment_id
    ).order_by(DeploymentHistory.created_at.desc()).all()
    
    return history

async def execute_deployment(deployment_id: int, db: Session):
    """Background task to execute deployment"""
    try:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return
        
        deployment.status = DeploymentStatus.DEPLOYING
        db.commit()
        
        # TODO: Actual deployment logic
        # For now, just simulate success
        import time
        time.sleep(2)
        
        deployment.status = DeploymentStatus.DEPLOYED
        deployment.deployed_at = datetime.now()
        deployment.deployment_log = {"message": "Deployment successful"}
        
        # Create history entry
        history = DeploymentHistory(
            deployment_id=deployment_id,
            event_type="deployed",
            from_status=DeploymentStatus.DEPLOYING.value,
            to_status=DeploymentStatus.DEPLOYED.value,
            created_by="system"
        )
        db.add(history)
        
        db.commit()
    except Exception as e:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = str(e)
        db.commit()
