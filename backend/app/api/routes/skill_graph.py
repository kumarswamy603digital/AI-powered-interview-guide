from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_hr_user
from app.core.skills import SKILL_CATEGORIES, adjacent_skills, canonical_skill
from app.core.workforce_intelligence import build_workforce_skill_graph
from app.crud.workforce import (
    create_skill_requirement,
    delete_skill_requirement,
    list_skill_requirements,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.workforce import (
    SkillGraphRead,
    SkillNodeRead,
    SkillRequirementCreate,
    SkillRequirementRead,
)


router = APIRouter(prefix="/api/skills", tags=["skill-graph"])

DbSessionDep = Annotated[Session, Depends(get_db)]
HrUserDep = Annotated[User, Depends(require_hr_user)]


@router.get("/graph", response_model=SkillGraphRead)
def read_skill_graph(db: DbSessionDep, hr_user: HrUserDep) -> SkillGraphRead:
    """
    The workforce skill graph: what the organisation has, what it needs now and
    in future, where the gaps are, and who could be reskilled to close them.
    """
    graph = build_workforce_skill_graph(db)
    return SkillGraphRead(
        nodes=[SkillNodeRead.model_validate(asdict(n)) for n in graph.nodes],
        edges=graph.edges,
        summary=graph.summary,
    )


@router.get("/gaps", response_model=List[SkillNodeRead])
def read_gaps(
    db: DbSessionDep,
    hr_user: HrUserDep,
    horizon: Optional[str] = Query(default=None, description="current|future"),
    only_critical: bool = Query(default=False),
) -> List[SkillNodeRead]:
    """Under-covered skills only, largest gap first."""
    graph = build_workforce_skill_graph(db)
    nodes = [n for n in graph.nodes if n.status in {"critical_gap", "at_risk"}]

    if horizon == "future":
        nodes = [n for n in nodes if n.gap_future > 0]
    elif horizon == "current":
        nodes = [n for n in nodes if n.gap_current > 0]
    if only_critical:
        nodes = [n for n in nodes if n.status == "critical_gap"]

    return [SkillNodeRead.model_validate(asdict(n)) for n in nodes]


@router.get("/categories", response_model=dict)
def read_categories(hr_user: HrUserDep) -> dict:
    """Skill taxonomy, which drives the reskilling adjacency suggestions."""
    return {
        "categories": [
            {"category": name, "skills": skills} for name, skills in SKILL_CATEGORIES.items()
        ]
    }


@router.get("/adjacent/{skill}", response_model=dict)
def read_adjacent(skill: str, hr_user: HrUserDep) -> dict:
    canonical = canonical_skill(skill)
    return {"skill": canonical, "adjacent_skills": adjacent_skills(canonical)}


# --------------------------------------------------------------------------
# Requirements (the demand side)
# --------------------------------------------------------------------------
@router.post(
    "/requirements", response_model=SkillRequirementRead, status_code=status.HTTP_201_CREATED
)
def add_requirement(
    payload: SkillRequirementCreate,
    db: DbSessionDep,
    hr_user: HrUserDep,
) -> SkillRequirementRead:
    requirement = create_skill_requirement(db, **payload.model_dump())
    return SkillRequirementRead.model_validate(requirement)


@router.get("/requirements", response_model=List[SkillRequirementRead])
def read_requirements(
    db: DbSessionDep,
    hr_user: HrUserDep,
    horizon: Optional[str] = Query(default=None),
    department: Optional[str] = Query(default=None),
) -> List[SkillRequirementRead]:
    return [
        SkillRequirementRead.model_validate(r)
        for r in list_skill_requirements(db, horizon=horizon, department=department)
    ]


@router.delete("/requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_requirement(requirement_id: int, db: DbSessionDep, hr_user: HrUserDep) -> None:
    if not delete_skill_requirement(db, requirement_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")
