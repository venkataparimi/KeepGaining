"""
Audit Trail API Routes
KeepGaining Trading Platform

Dedicated endpoints for audit trail operations.
"""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import json
import io

from app.services.audit_trail import (
    get_audit_trail,
    AuditEventType,
)

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("/logs")
async def get_audit_logs(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get paginated audit logs with filtering."""
    trail = get_audit_trail()
    
    # Parse dates if provided
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    # Parse event type if provided
    event_types = [AuditEventType(event_type)] if event_type else None
    
    # Get events
    events = await trail.query_events(
        event_types=event_types,
        start_time=start_dt,
        end_time=end_dt,
        limit=limit + 1,  # Get one extra to check if there are more
    )
    
    # Apply offset (simple implementation - in production use DB offset)
    events = events[offset:offset + limit + 1]
    has_more = len(events) > limit
    events = events[:limit]
    
    total = len(events) + offset + (1 if has_more else 0)
    pages = (total + limit - 1) // limit if limit > 0 else 1
    
    return {
        "logs": [e.to_dict() for e in events],
        "total": total,
        "page": (offset // limit) + 1 if limit > 0 else 1,
        "pages": pages,
    }


@router.get("/stats")
async def get_audit_stats():
    """Get audit trail statistics."""
    trail = get_audit_trail()
    stats = trail.get_stats()
    
    # Get events by day (last 7 days)
    events_by_day = []
    events = await trail.query_events(limit=1000)
    
    # Group by date
    day_counts = {}
    for event in events:
        day = event.timestamp.date().isoformat() if hasattr(event, 'timestamp') else None
        if day:
            day_counts[day] = day_counts.get(day, 0) + 1
    
    # Sort and format
    for date_str in sorted(day_counts.keys())[-7:]:
        events_by_day.append({"date": date_str, "count": day_counts[date_str]})
    
    # Events by type
    events_by_type = {}
    for event in events:
        event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
        events_by_type[event_type] = events_by_type.get(event_type, 0) + 1
    
    return {
        "total_events": stats.get("total_events", len(events)),
        "events_by_type": events_by_type,
        "events_by_day": events_by_day,
    }


@router.get("/export")
async def export_audit_logs(
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    format: str = Query(default="json", pattern="^(json|csv)$"),
):
    """Export audit logs as JSON or CSV."""
    trail = get_audit_trail()
    
    # Parse dates
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    # Parse event type
    event_types = [AuditEventType(event_type)] if event_type else None
    
    # Get all matching events
    events = await trail.query_events(
        event_types=event_types,
        start_time=start_dt,
        end_time=end_dt,
        limit=10000,
    )
    
    event_data = [e.to_dict() for e in events]
    
    if format == "csv":
        # Generate CSV
        output = io.StringIO()
        if event_data:
            headers = list(event_data[0].keys())
            output.write(",".join(headers) + "\n")
            for row in event_data:
                values = [str(row.get(h, "")).replace(",", ";").replace("\n", " ") for h in headers]
                output.write(",".join(values) + "\n")
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )
    else:
        # JSON format
        return StreamingResponse(
            io.BytesIO(json.dumps(event_data, default=str, indent=2).encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit_logs.json"},
        )
