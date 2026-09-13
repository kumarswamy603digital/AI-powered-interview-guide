from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.crud.workforce import (
    bulk_record_attendance,
    get_employee,
    list_attendance,
    record_attendance,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.workforce import (
    AttendanceBulkCreate,
    AttendanceCreate,
    AttendanceRead,
)


router = APIRouter(prefix="/api/attendance", tags=["attendance"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


@router.post("", response_model=AttendanceRead, status_code=status.HTTP_201_CREATED)
def add_attendance(
    payload: AttendanceCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> AttendanceRead:
    if get_employee(db, payload.employee_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    try:
        record = record_attendance(db, **payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Attendance for {payload.work_date} already recorded for this employee.",
        )
    return AttendanceRead.model_validate(record)


@router.post("/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_attendance_bulk(
    payload: AttendanceBulkCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> dict:
    """Import many attendance days at once."""
    employee_ids = {row.employee_id for row in payload.records}
    for employee_id in employee_ids:
        if get_employee(db, employee_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Employee {employee_id} not found"
            )
    try:
        inserted = bulk_record_attendance(db, [row.model_dump() for row in payload.records])
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more days are already recorded for these employees.",
        )
    return {"inserted": inserted, "employees": len(employee_ids)}


@router.get("/{employee_id}", response_model=List[AttendanceRead])
def read_attendance(
    employee_id: int,
    db: DbSessionDep,
    hr_user: HrUserDep,
    days: int = Query(default=90, ge=1, le=730),
    since: Optional[date] = Query(default=None),
) -> List[AttendanceRead]:
    if get_employee(db, employee_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    window_start = since or (date.today() - timedelta(days=days))
    records = list_attendance(db, employee_id, since=window_start, limit=days + 10)
    return [AttendanceRead.model_validate(r) for r in records]
