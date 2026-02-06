from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Iterable, List, Tuple

from app.core.report import generate_report
from app.crud.interview import list_turns
from app.models.interview import InterviewSession
from app.schemas.analytics import (
    InterviewHistoryItem,
    PerformanceTrendPoint,
    SkillProgressItem,
)


def _session_report_pair(
    session: InterviewSession,
    *,
    db,
):
    turns = list_turns(db, session_id=session.id)
    transcript = [{"role": t.role, "content": t.content} for t in turns]
    report = generate_report(
        interview_id=session.id,
        target_role=session.target_role,
        difficulty=session.difficulty,
        personality_mode=session.personality_mode,
        transcript=transcript,
    )
    return session, turns, report


def build_interview_history(
    sessions: Iterable[InterviewSession],
    *,
    db,
) -> List[InterviewHistoryItem]:
    items: List[InterviewHistoryItem] = []
    for session in sessions:
        turns = list_turns(db, session_id=session.id)
        items.append(
            InterviewHistoryItem(
                id=session.id,
                target_role=session.target_role,
                difficulty=session.difficulty,
                personality_mode=session.personality_mode,
                status=session.status,
                started_at=session.started_at,
                ended_at=session.ended_at,
                total_turns=len(turns),
            )
        )
    return items


def build_skill_progress(
    sessions: Iterable[InterviewSession],
    *,
    db,
) -> List[SkillProgressItem]:
    # Collect scores per skill across sessions
    skill_scores: dict[str, List[Tuple[int, float]]] = defaultdict(list)

    for session in sessions:
        _, _, report = _session_report_pair(session, db=db)
        for skill in report.skill_breakdown:
            skill_scores[skill.name].append((session.id, skill.score))

    items: List[SkillProgressItem] = []
    for name, values in skill_scores.items():
        # values is list of (interview_id, score) in session order already
        scores = [v[1] for v in values]
        avg = mean(scores)
        latest = scores[-1]
        if len(scores) >= 2:
            if latest > scores[0] + 3:
                trend = "up"
            elif latest < scores[0] - 3:
                trend = "down"
            else:
                trend = "flat"
        else:
            trend = "flat"

        items.append(
            SkillProgressItem(
                skill_name=name,
                average_score=round(avg, 2),
                latest_score=round(latest, 2),
                trend=trend,
            )
        )

    return items


def build_performance_trends(
    sessions: Iterable[InterviewSession],
    *,
    db,
) -> List[PerformanceTrendPoint]:
    points: List[PerformanceTrendPoint] = []

    for session in sessions:
        _, _, report = _session_report_pair(session, db=db)
        if not report.skill_breakdown:
            continue
        avg_score = mean(s.score for s in report.skill_breakdown)
        points.append(
            PerformanceTrendPoint(
                interview_id=session.id,
                date=session.started_at,
                average_skill_score=round(avg_score, 2),
            )
        )

    return points

