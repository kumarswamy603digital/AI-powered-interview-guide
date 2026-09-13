from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.core.policy_qa import answer_policy_question, split_policy_into_chunks
from app.core.workforce_intelligence import (
    build_employee_context,
    build_policy_chunk_inputs,
)
from app.crud.workforce import (
    create_policy,
    delete_policy,
    get_employee,
    get_policy,
    list_policies,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.policy import (
    PolicyAnswerRead,
    PolicyAskRequest,
    PolicyChunkRead,
    PolicyCreate,
    PolicyDetailRead,
    PolicyRead,
)


router = APIRouter(prefix="/api/policies", tags=["policies"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


def _to_read(policy) -> PolicyRead:
    payload = PolicyRead.model_validate(policy)
    payload.section_count = len(policy.chunks or [])
    return payload


@router.post("", response_model=PolicyDetailRead, status_code=status.HTTP_201_CREATED)
def add_policy(payload: PolicyCreate, db: DbSessionDep, hr_user: HrUserDep) -> PolicyDetailRead:
    """
    Add a policy.

    The raw text is split into numbered sections on save so answers can cite an
    exact clause rather than a whole document.
    """
    chunks = split_policy_into_chunks(payload.content)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract any sections from the supplied content.",
        )

    policy = create_policy(
        db,
        chunks=chunks,
        title=payload.title,
        category=payload.category,
        version=payload.version,
        effective_date=payload.effective_date,
        applies_to=payload.applies_to,
        source_url=payload.source_url,
    )

    detail = PolicyDetailRead.model_validate(policy)
    detail.section_count = len(policy.chunks or [])
    detail.chunks = [PolicyChunkRead.model_validate(c) for c in policy.chunks]
    return detail


@router.get("", response_model=List[PolicyRead])
def read_policies(
    db: DbSessionDep,
    hr_user: HrUserDep,
    category: Optional[str] = Query(default=None),
) -> List[PolicyRead]:
    return [_to_read(p) for p in list_policies(db, category=category)]


@router.post("/ask", response_model=PolicyAnswerRead)
def ask_policy(
    payload: PolicyAskRequest,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> PolicyAnswerRead:
    """
    Answer a policy question with citations.

    Returns `answered: false` and escalates when no policy covers the question,
    rather than producing a confident-sounding guess. When `employee_id` is given,
    the answer is scoped to that employee and flags policies aimed at a different
    population.
    """
    context = None
    if payload.employee_id is not None:
        employee = get_employee(db, payload.employee_id)
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        context = build_employee_context(db, employee)

    answer = answer_policy_question(
        payload.question,
        build_policy_chunk_inputs(db),
        context=context,
        top_k=payload.top_k,
        use_llm=payload.use_llm,
    )
    return PolicyAnswerRead.model_validate(asdict(answer))


@router.get("/{policy_id}", response_model=PolicyDetailRead)
def read_policy(policy_id: int, db: DbSessionDep, hr_user: HrUserDep) -> PolicyDetailRead:
    policy = get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    detail = PolicyDetailRead.model_validate(policy)
    detail.section_count = len(policy.chunks or [])
    detail.chunks = [PolicyChunkRead.model_validate(c) for c in policy.chunks]
    return detail


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_policy(policy_id: int, db: DbSessionDep, hr_user: HrUserDep) -> None:
    policy = get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    delete_policy(db, policy)
