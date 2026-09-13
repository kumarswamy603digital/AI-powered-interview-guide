from __future__ import annotations

"""
Skill extraction and matching.

This module is intentionally dependency-free and deterministic: skill matching
drives hiring recommendations, so it must be reproducible and explainable rather
than depending on an LLM call that may vary between runs.
"""

import re
from typing import Dict, Iterable, List, Optional, Tuple


# Canonical skill name -> aliases that should map to it.
# Only the canonical name is ever surfaced to the UI.
SKILL_ALIASES: Dict[str, List[str]] = {
    # Languages
    "Python": ["python", "python3"],
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java"],
    "Go": ["golang", "go lang"],
    "Rust": ["rust"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", ".net", "dotnet"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Scala": ["scala"],
    "SQL": ["sql"],
    "R": ["r language"],
    # Frontend
    "React": ["react", "react.js", "reactjs"],
    "Angular": ["angular", "angularjs"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Next.js": ["next.js", "nextjs"],
    "HTML/CSS": ["html", "css", "html5", "css3", "scss", "sass", "tailwind"],
    "Redux": ["redux"],
    # Backend / frameworks
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Express": ["express", "express.js", "expressjs"],
    "GraphQL": ["graphql"],
    "REST APIs": ["rest", "rest api", "rest apis", "restful"],
    "gRPC": ["grpc"],
    "Microservices": ["microservices", "microservice"],
    # Data stores
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "opensearch"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],
    "SQLite": ["sqlite"],
    "Snowflake": ["snowflake"],
    # Cloud / infra
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Docker": ["docker", "containerization"],
    "Kubernetes": ["kubernetes", "k8s", "eks", "gke"],
    "Terraform": ["terraform"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "jenkins", "github actions", "gitlab ci"],
    "Linux": ["linux", "unix"],
    "Nginx": ["nginx"],
    "Serverless": ["serverless"],
    # Data / ML
    "Machine Learning": ["machine learning", "ml", "deep learning"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch", "torch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Spark": ["spark", "pyspark", "apache spark"],
    "Airflow": ["airflow", "apache airflow"],
    "Kafka": ["kafka", "apache kafka"],
    "ETL": ["etl", "elt", "data pipeline", "data pipelines"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "LLMs": ["llm", "llms", "large language model", "large language models", "genai", "generative ai"],
    "RAG": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    # Practices / tooling
    "Git": ["git", "github", "gitlab", "version control"],
    "Agile/Scrum": ["agile", "scrum", "kanban", "sprint planning"],
    "Testing": ["unit testing", "pytest", "jest", "test automation", "tdd", "junit"],
    "System Design": ["system design", "distributed systems", "architecture design"],
    "Observability": ["observability", "monitoring", "prometheus", "grafana", "datadog"],
    "Security": ["security", "owasp", "penetration testing", "appsec"],
    # HR-domain / soft skills (kept coarse on purpose)
    "Communication": ["communication", "stakeholder management", "presentation skills"],
    "Leadership": ["leadership", "team lead", "mentoring", "people management"],
    "Project Management": ["project management", "jira", "roadmap planning"],
    "Recruitment": ["recruitment", "recruiting", "talent acquisition", "sourcing"],
    "HRIS": ["hris", "workday", "successfactors", "bamboohr"],
    "Payroll": ["payroll", "compensation", "benefits administration"],
    "Onboarding": ["onboarding", "employee onboarding"],
}


# Cheap reverse index built once at import time.
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canonical, _aliases in SKILL_ALIASES.items():
    _ALIAS_TO_CANONICAL[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias] = _canonical


def normalize(value: str) -> str:
    """Lowercase, collapse whitespace and strip surrounding punctuation."""
    cleaned = (value or "").strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" .,;:•-|/")


def canonical_skill(value: str) -> str:
    """
    Map a free-text skill to its canonical form.

    Unknown skills are title-cased rather than dropped, so an HR user can require
    a skill the built-in vocabulary has never seen.
    """
    norm = normalize(value)
    if not norm:
        return ""
    if norm in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[norm]
    # Preserve the author's capitalisation for unknown multi-word skills.
    return " ".join(part.capitalize() if part.islower() else part for part in value.strip().split())


def _alias_pattern(alias: str) -> str:
    """
    Word-boundary pattern that also works for aliases containing '+', '#' or '.'
    (\\b misbehaves around non-word characters, e.g. 'c++').
    """
    escaped = re.escape(alias)
    return rf"(?<![\w+#]){escaped}(?![\w+#])"


def _aliases_for(skill: str) -> List[str]:
    canonical = canonical_skill(skill)
    aliases = {normalize(canonical)}
    for alias in SKILL_ALIASES.get(canonical, []):
        aliases.add(normalize(alias))
    aliases.discard("")
    return sorted(aliases, key=len, reverse=True)


def skill_in_text(skill: str, text: str) -> bool:
    """True when the skill (or any known alias) appears in the text."""
    if not skill or not text:
        return False
    haystack = normalize(text)
    for alias in _aliases_for(skill):
        if re.search(_alias_pattern(alias), haystack):
            return True
    return False


def extract_skills(text: str) -> List[str]:
    """
    Extract canonical skills from free-form resume text.

    Returns canonical names sorted alphabetically. Only skills in the built-in
    vocabulary are detected; job-specific requirements are matched separately by
    match_skills(), which also searches the raw text.
    """
    if not text:
        return []
    haystack = normalize(text)
    found: set[str] = set()
    for canonical, aliases in SKILL_ALIASES.items():
        candidates = [normalize(canonical), *(normalize(a) for a in aliases)]
        for alias in candidates:
            if not alias:
                continue
            if re.search(_alias_pattern(alias), haystack):
                found.add(canonical)
                break
    return sorted(found)


def match_skills(
    required: Iterable[str],
    *,
    resume_text: str = "",
    known_skills: Optional[Iterable[str]] = None,
) -> Tuple[List[str], List[str]]:
    """
    Split required skills into (matched, missing).

    A requirement counts as matched when it appears in the candidate's extracted
    skill list or anywhere in the resume text. Both are checked because HR can
    require skills that are not in the built-in vocabulary.
    """
    known_canonical = {canonical_skill(s) for s in (known_skills or []) if s}
    matched: List[str] = []
    missing: List[str] = []

    seen: set[str] = set()
    for raw in required or []:
        canonical = canonical_skill(raw)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)

        if canonical in known_canonical or skill_in_text(canonical, resume_text):
            matched.append(canonical)
        else:
            missing.append(canonical)

    return matched, missing


_YEARS_PATTERNS = [
    re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs|year)\b"),
    re.compile(r"\b(?:over|more than|about|approx(?:imately)?)\s+(\d{1,2})\s*(?:years|yrs)\b"),
]


def extract_years_experience(text: str) -> Optional[float]:
    """
    Best-effort total years of experience from resume text.

    Returns the largest plausible figure found (resumes usually state the
    headline total, then smaller per-role durations). None when nothing is found,
    which callers must treat as 'unknown' rather than zero.
    """
    if not text:
        return None
    haystack = normalize(text)
    values: List[float] = []
    for pattern in _YEARS_PATTERNS:
        for match in pattern.finditer(haystack):
            try:
                value = float(match.group(1))
            except (TypeError, ValueError):
                continue
            if 0 < value <= 50:
                values.append(value)
    if not values:
        return None
    return max(values)
