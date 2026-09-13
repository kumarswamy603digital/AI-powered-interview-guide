from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Dict, Iterable, List, Optional, Tuple

from app.crud.interview import list_turns
from app.models.interview import InterviewSession
from app.schemas.analytics import (
    InterviewHistoryItem,
    PerformanceTrendPoint,
    SkillProgressItem,
)


def _persisted_skill_scores(session: InterviewSession) -> Dict[str, float]:
    """
    Read the scores stored when the interview ended.

    Previously every analytics request regenerated the full report for every
    session, which meant one Gemini call per session per page load and scores that
    could change between requests. Sessions that ended before scores were
    persisted (or that never ended) are skipped rather than re-scored.
    """
    result: Dict[str, float] = {}
    for entry in session.skill_scores or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        raw = entry.get("score")
        if not name or raw is None:
            continue
        try:
            result[name] = float(raw)
        except (TypeError, ValueError):
            continue
    return result


def _session_overall(session: InterviewSession) -> Optional[float]:
    if session.overall_score is not None:
        return float(session.overall_score)
    scores = _persisted_skill_scores(session)
    return mean(scores.values()) if scores else None


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
    # Collect persisted scores per skill across sessions.
    skill_scores: dict[str, List[Tuple[int, float]]] = defaultdict(list)

    for session in sessions:
        for name, score in _persisted_skill_scores(session).items():
            skill_scores[name].append((session.id, score))

    items: List[SkillProgressItem] = []
    for name, values in skill_scores.items():
        # values is a list of (interview_id, score) in session order already
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
        overall = _session_overall(session)
        if overall is None:
            # Not scored yet (still active, or ended before scoring existed).
            continue
        points.append(
            PerformanceTrendPoint(
                interview_id=session.id,
                date=session.started_at,
                average_skill_score=round(overall, 2),
            )
        )

    return points
