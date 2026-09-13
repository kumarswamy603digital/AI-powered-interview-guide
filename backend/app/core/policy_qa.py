from __future__ import annotations

"""
HR policy reasoning.

Answers policy questions with source-backed citations, and refuses to answer when
no policy covers the question - a wrong answer about leave entitlement or notice
period is worse than no answer.

Retrieval is IDF-weighted term matching over policy sections, implemented here
rather than with an external vector store so the agent has no runtime
dependencies and stays deterministic. When a Gemini key is configured the
retrieved sections are synthesised into prose; otherwise an extractive answer is
composed from the sections themselves. Either way the citations are the same.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence, Tuple


# Below this score the top match is treated as noise rather than an answer.
MIN_RELEVANCE_SCORE = 1.5
# Minimum share of meaningful query terms that must appear somewhere in the
# retrieved sections before an answer is attempted.
MIN_TERM_COVERAGE = 0.34

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "get", "how", "i", "if", "in", "is", "it", "its", "many", "me",
    "much", "my", "of", "on", "or", "our", "should", "so", "than", "that", "the",
    "their", "then", "there", "these", "they", "this", "to", "was", "we", "what",
    "when", "where", "which", "who", "will", "with", "would", "you", "your", "am",
    "any", "about", "have", "has", "had", "need", "want", "please", "tell",
}

# Query expansion: employees rarely use the vocabulary a policy is written in.
SYNONYMS: Dict[str, List[str]] = {
    "vacation": ["leave", "annual", "holiday", "pto"],
    "holiday": ["leave", "annual", "vacation"],
    "pto": ["leave", "annual", "vacation"],
    "sick": ["illness", "medical", "sickness"],
    "wfh": ["remote", "home", "telework"],
    "remote": ["home", "telework", "wfh"],
    "maternity": ["parental", "childbirth", "adoption"],
    "paternity": ["parental", "childbirth", "adoption"],
    "notice": ["resignation", "termination", "separation"],
    "quit": ["resignation", "notice", "separation"],
    "resign": ["resignation", "notice", "separation"],
    "expense": ["reimbursement", "claim", "receipt"],
    "reimburse": ["expense", "claim", "receipt"],
    "travel": ["trip", "expense", "accommodation"],
    "bonus": ["incentive", "variable", "payout"],
    "salary": ["compensation", "pay", "remuneration"],
    "raise": ["increment", "revision", "compensation"],
    "promotion": ["advancement", "progression", "band"],
    "harassment": ["misconduct", "grievance", "conduct"],
    "complaint": ["grievance", "escalation", "report"],
    "probation": ["probationary", "confirmation"],
    "referral": ["refer", "bonus", "candidate"],
    "training": ["learning", "development", "course"],
    "laptop": ["equipment", "asset", "device"],
    "carry": ["carryover", "carryforward", "accrual"],
    "encash": ["encashment", "payout"],
}

_TOKEN_RE = re.compile(r"[a-z0-9']+")

# Suffix rules applied longest-first. Deliberately aggressive: for policy
# retrieval, missing "submitted" when the employee typed "submit" is a far worse
# failure than the occasional loose match, because a missed match becomes a
# refusal on a question the library actually answers.
_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("ities", "ity"),
    ("ations", "ation"),
    ("ements", "ement"),
    ("ement", ""),
    ("ments", "ment"),
    ("ment", ""),
    ("ingly", ""),
    ("edly", ""),
    ("ies", "y"),
    ("ied", "y"),
    ("ing", ""),
    ("est", ""),
    ("ers", ""),
    ("ed", ""),
    ("er", ""),
    ("ly", ""),
    ("es", ""),
    ("s", ""),
)


def _stem(token: str) -> str:
    """
    Lightweight suffix stripper.

    Not linguistically correct - it only needs to map the inflections of the same
    word onto one key, consistently on both the query and the document side
    ('claim'/'claims', 'submit'/'submitted', 'late'/'later').
    """
    stem = token
    for suffix, replacement in _SUFFIX_RULES:
        if stem.endswith(suffix) and len(stem) - len(suffix) >= 3:
            stem = stem[: -len(suffix)] + replacement
            break
    # 'submitt' -> 'submit'
    if len(stem) >= 4 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
        stem = stem[:-1]
    # 'late' -> 'lat' so it meets 'later'; 'reimburse' -> 'reimburs' meets 'reimbursed'
    if len(stem) >= 4 and stem.endswith("e"):
        stem = stem[:-1]
    return stem


@dataclass
class PolicyChunkInput:
    chunk_id: Optional[int] = None
    policy_id: Optional[int] = None
    policy_title: str = ""
    category: Optional[str] = None
    section: Optional[str] = None
    content: str = ""
    version: Optional[str] = None
    effective_date: Optional[str] = None
    applies_to: Optional[str] = None


@dataclass
class EmployeeContext:
    """Optional context so answers can be scoped to the person asking."""

    employee_id: Optional[int] = None
    full_name: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    department: Optional[str] = None
    tenure_years: Optional[float] = None


@dataclass
class Citation:
    marker: str
    policy_id: Optional[int]
    policy_title: str
    section: Optional[str]
    version: Optional[str]
    effective_date: Optional[str]
    relevance: float
    excerpt: str


@dataclass
class PolicyAnswer:
    question: str
    answered: bool
    answer: str
    citations: List[Citation]
    confidence: Literal["high", "medium", "low"]
    matched_terms: List[str]
    unmatched_terms: List[str]
    related_policies: List[str]
    caveats: List[str]
    generated_by: Literal["gemini", "extractive", "refusal"]
    follow_up_suggestions: List[str] = field(default_factory=list)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _stems(text: str) -> List[str]:
    """Stemmed tokens for matching. Used on both queries and documents."""
    return [_stem(token) for token in _tokenize(text)]


def _meaningful_terms(text: str) -> List[str]:
    """Original (unstemmed) query words, so the UI can echo what the user typed."""
    seen: List[str] = []
    for token in _tokenize(text):
        if token in STOPWORDS or len(token) < 2:
            continue
        if token not in seen:
            seen.append(token)
    return seen


def _expand(terms: Sequence[str]) -> List[str]:
    expanded = list(terms)
    for term in terms:
        for synonym in SYNONYMS.get(term, []):
            if synonym not in expanded:
                expanded.append(synonym)
    return expanded


def _stem_map(terms: Sequence[str]) -> Dict[str, str]:
    """
    stem -> the original word that produced it.

    Matching happens on stems, but everything reported back to the caller uses
    the word the user actually typed.
    """
    mapping: Dict[str, str] = {}
    for term in terms:
        mapping.setdefault(_stem(term), term)
    return mapping


def _build_idf(chunks: Sequence[PolicyChunkInput]) -> Dict[str, float]:
    """Inverse document frequency over sections, so 'leave' outweighs 'employee'."""
    document_count = max(1, len(chunks))
    frequencies: Dict[str, int] = {}
    for chunk in chunks:
        for token in set(_stems(f"{chunk.policy_title} {chunk.section or ''} {chunk.content}")):
            frequencies[token] = frequencies.get(token, 0) + 1
    return {
        token: math.log(1.0 + document_count / (1 + count))
        for token, count in frequencies.items()
    }


def _score_chunk(
    chunk: PolicyChunkInput,
    *,
    query_terms: Sequence[str],
    original_terms: Sequence[str],
    idf: Dict[str, float],
    context: Optional[EmployeeContext],
) -> Tuple[float, List[str]]:
    content_tokens = _stems(chunk.content)
    if not content_tokens:
        return 0.0, []

    counts: Dict[str, int] = {}
    for token in content_tokens:
        counts[token] = counts.get(token, 0) + 1

    title_tokens = set(_stems(f"{chunk.policy_title} {chunk.section or ''} {chunk.category or ''}"))
    original_stems = {_stem(t) for t in original_terms}

    score = 0.0
    matched: List[str] = []
    for term in query_terms:
        stem = _stem(term)
        weight = idf.get(stem, 0.6)
        # Original query terms count for more than synonym expansions.
        if stem not in original_stems:
            weight *= 0.6

        term_score = 0.0
        if stem in counts:
            # Saturating term frequency: a section repeating a word 20 times is
            # not 20 times more relevant.
            term_score += weight * (1.0 + math.log(counts[stem]))
        if stem in title_tokens:
            term_score += weight * 1.5  # a heading match is a strong signal
        if term_score > 0:
            score += term_score
            matched.append(term)

    # Mild length normalisation so short, precise sections are not buried by long ones.
    score = score / (1.0 + math.log(1.0 + len(content_tokens) / 120.0))

    if context:
        applies = (chunk.applies_to or "").strip().lower()
        if applies and applies not in {"all", "everyone", "*"}:
            haystack = " ".join(
                v.lower() for v in [context.location, context.employment_type, context.department] if v
            )
            if haystack and any(part.strip() in haystack for part in applies.split(",") if part.strip()):
                score *= 1.25  # policy specifically covers this person
            elif haystack:
                score *= 0.7  # scoped to a different population

    return score, matched


def retrieve_policy_chunks(
    question: str,
    chunks: Sequence[PolicyChunkInput],
    *,
    context: Optional[EmployeeContext] = None,
    top_k: int = 4,
) -> List[Tuple[PolicyChunkInput, float, List[str]]]:
    """Rank policy sections against a question, most relevant first."""
    original_terms = _meaningful_terms(question)
    if not original_terms or not chunks:
        return []

    query_terms = _expand(original_terms)
    idf = _build_idf(chunks)

    scored: List[Tuple[PolicyChunkInput, float, List[str]]] = []
    for chunk in chunks:
        score, matched = _score_chunk(
            chunk,
            query_terms=query_terms,
            original_terms=original_terms,
            idf=idf,
            context=context,
        )
        if score > 0:
            scored.append((chunk, round(score, 4), matched))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def _relevant_sentences(content: str, terms: Sequence[str], limit: int = 2) -> List[str]:
    """Sentences from a section that actually address the query terms."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", content or "") if s.strip()]
    stems = {_stem(t) for t in terms}
    scored: List[Tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        tokens = set(_stems(sentence))
        hits = sum(1 for stem in stems if stem in tokens)
        if hits:
            scored.append((hits, -index, sentence))
    scored.sort(reverse=True)
    if not scored:
        return sentences[:1]
    return [sentence for _, _, sentence in scored[:limit]]


def _build_citations(
    results: Sequence[Tuple[PolicyChunkInput, float, List[str]]],
) -> List[Citation]:
    citations: List[Citation] = []
    for index, (chunk, score, matched) in enumerate(results, start=1):
        excerpt = " ".join(_relevant_sentences(chunk.content, matched, limit=2))
        if len(excerpt) > 400:
            excerpt = excerpt[:397] + "..."
        citations.append(
            Citation(
                marker=f"[{index}]",
                policy_id=chunk.policy_id,
                policy_title=chunk.policy_title,
                section=chunk.section,
                version=chunk.version,
                effective_date=chunk.effective_date,
                relevance=score,
                excerpt=excerpt,
            )
        )
    return citations


def _context_caveats(
    results: Sequence[Tuple[PolicyChunkInput, float, List[str]]],
    context: Optional[EmployeeContext],
) -> List[str]:
    caveats: List[str] = []
    if not context:
        return caveats

    person_scope = " ".join(
        v.lower() for v in [context.location, context.employment_type, context.department] if v
    )
    for chunk, _score, _matched in results:
        applies = (chunk.applies_to or "").strip()
        if not applies or applies.lower() in {"all", "everyone", "*"}:
            continue
        parts = [p.strip().lower() for p in applies.split(",") if p.strip()]
        if person_scope and not any(part in person_scope for part in parts):
            caveats.append(
                f"'{chunk.policy_title}' applies to {applies}; confirm it covers "
                f"{context.full_name or 'this employee'}"
                + (f" ({context.location})" if context.location else "")
                + "."
            )
    # De-duplicate while preserving order.
    seen: set = set()
    unique: List[str] = []
    for caveat in caveats:
        if caveat not in seen:
            seen.add(caveat)
            unique.append(caveat)
    return unique


def _extractive_answer(
    question: str,
    results: Sequence[Tuple[PolicyChunkInput, float, List[str]]],
) -> str:
    """Compose an answer directly from the retrieved sections, with markers."""
    lines: List[str] = []
    for index, (chunk, _score, matched) in enumerate(results, start=1):
        sentences = _relevant_sentences(chunk.content, matched, limit=2)
        if not sentences:
            continue
        location = chunk.policy_title
        if chunk.section:
            location += f" — {chunk.section}"
        lines.append(f"According to {location} [{index}]: " + " ".join(sentences))
    if not lines:
        return "No policy section directly addresses this question."
    return "\n\n".join(lines)


def _gemini_answer(
    question: str,
    results: Sequence[Tuple[PolicyChunkInput, float, List[str]]],
    context: Optional[EmployeeContext],
) -> Optional[str]:
    """
    Synthesise the retrieved sections into prose.

    Imports are local so this module stays importable (and testable) without the
    application settings or the Gemini SDK present.
    """
    try:
        from app.core.config import settings
    except Exception:  # pragma: no cover - settings unavailable
        return None
    if not getattr(settings, "GEMINI_API_KEY", None):
        return None
    try:
        import google.generativeai as genai
    except Exception:  # pragma: no cover - optional dependency
        return None

    sources = []
    for index, (chunk, _score, _matched) in enumerate(results, start=1):
        header = chunk.policy_title + (f" — {chunk.section}" if chunk.section else "")
        sources.append(f"[{index}] {header}\n{chunk.content}")

    who = ""
    if context:
        bits = [b for b in [context.employment_type, context.location, context.department] if b]
        if bits:
            who = f"\nThe employee asking is: {', '.join(bits)}."

    prompt = f"""You are an HR policy assistant. Answer ONLY from the policy extracts provided.

Question: {question}{who}

Policy extracts:
{chr(10).join(sources)}

Rules:
- Cite the extract you used with its bracket marker, e.g. [1], after each claim.
- If the extracts do not answer the question, reply exactly: NOT_COVERED
- Do not invent numbers, entitlements, or deadlines that are not in the extracts.
- Be concise and specific. Prefer exact figures and timeframes from the text.
"""
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
    except Exception:
        return None

    if not text or "NOT_COVERED" in text.upper():
        return None
    return text


def answer_policy_question(
    question: str,
    chunks: Sequence[PolicyChunkInput],
    *,
    context: Optional[EmployeeContext] = None,
    top_k: int = 4,
    use_llm: bool = True,
) -> PolicyAnswer:
    """
    Answer an HR policy question from the policy library.

    Refuses rather than guesses when retrieval finds nothing relevant, so an
    unanswerable question never produces a confident-sounding fabrication.
    """
    original_terms = _meaningful_terms(question)
    results = retrieve_policy_chunks(question, chunks, context=context, top_k=top_k)

    matched_terms: List[str] = []
    for _chunk, _score, matched in results:
        for term in matched:
            if term in original_terms and term not in matched_terms:
                matched_terms.append(term)
    unmatched_terms = [t for t in original_terms if t not in matched_terms]

    coverage = (len(matched_terms) / len(original_terms)) if original_terms else 0.0
    top_score = results[0][1] if results else 0.0

    if not results or top_score < MIN_RELEVANCE_SCORE or coverage < MIN_TERM_COVERAGE:
        available = sorted({c.policy_title for c in chunks})
        return PolicyAnswer(
            question=question,
            answered=False,
            answer=(
                "No policy in the library covers this question. Rather than infer an "
                "answer, escalate to an HR partner so the response is authoritative."
                + (
                    f" Closest available policies: {', '.join(available[:5])}."
                    if available
                    else " The policy library is currently empty."
                )
            ),
            citations=_build_citations(results[:2]) if results else [],
            confidence="low",
            matched_terms=matched_terms,
            unmatched_terms=unmatched_terms,
            related_policies=available[:5],
            caveats=["Unanswered questions should be logged so the policy library can be extended."],
            generated_by="refusal",
            follow_up_suggestions=[
                f"Is there a policy covering {term}?" for term in unmatched_terms[:2]
            ],
        )

    citations = _build_citations(results)
    caveats = _context_caveats(results, context)

    answer_text: Optional[str] = None
    generated_by: Literal["gemini", "extractive", "refusal"] = "extractive"
    if use_llm:
        answer_text = _gemini_answer(question, results, context)
        if answer_text:
            generated_by = "gemini"
    if not answer_text:
        answer_text = _extractive_answer(question, results)

    # Confidence reflects retrieval quality and the margin over the next match.
    margin = top_score - (results[1][1] if len(results) > 1 else 0.0)
    if coverage >= 0.7 and top_score >= MIN_RELEVANCE_SCORE * 2 and margin > 0.5:
        confidence: Literal["high", "medium", "low"] = "high"
    elif coverage >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"
    if caveats and confidence == "high":
        confidence = "medium"

    related = []
    for chunk, _score, _matched in results:
        if chunk.policy_title not in related:
            related.append(chunk.policy_title)

    return PolicyAnswer(
        question=question,
        answered=True,
        answer=answer_text,
        citations=citations,
        confidence=confidence,
        matched_terms=matched_terms,
        unmatched_terms=unmatched_terms,
        related_policies=related,
        caveats=caveats,
        generated_by=generated_by,
    )


def split_policy_into_chunks(
    content: str,
    *,
    max_chars: int = 1200,
) -> List[Tuple[Optional[str], str]]:
    """
    Split raw policy text into (section_heading, body) pairs.

    Headings are detected from numbered clauses ("3.2 Carry-forward") and short
    title-style lines, so an uploaded policy becomes citable without manual
    sectioning. Long sections are split further to keep citations precise.
    """
    lines = (content or "").splitlines()
    sections: List[Tuple[Optional[str], List[str]]] = []
    current_heading: Optional[str] = None
    current_body: List[str] = []

    heading_re = re.compile(r"^\s*(\d+(\.\d+)*\.?\s+.{2,80}|[A-Z][A-Za-z /&-]{2,60}:?)\s*$")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        is_heading = bool(heading_re.match(stripped)) and len(stripped.split()) <= 12
        if is_heading and not stripped.endswith("."):
            if current_body:
                sections.append((current_heading, current_body))
                current_body = []
            current_heading = stripped.rstrip(":")
        else:
            current_body.append(stripped)

    if current_body:
        sections.append((current_heading, current_body))

    chunks: List[Tuple[Optional[str], str]] = []
    for heading, body_lines in sections:
        body = " ".join(body_lines).strip()
        if not body:
            continue
        if len(body) <= max_chars:
            chunks.append((heading, body))
            continue
        # Split oversized sections on sentence boundaries.
        sentences = re.split(r"(?<=[.!?])\s+", body)
        buffer = ""
        part = 1
        for sentence in sentences:
            if buffer and len(buffer) + len(sentence) + 1 > max_chars:
                label = f"{heading} (part {part})" if heading else f"Part {part}"
                chunks.append((label, buffer.strip()))
                buffer = sentence
                part += 1
            else:
                buffer = f"{buffer} {sentence}".strip()
        if buffer:
            label = f"{heading} (part {part})" if heading and part > 1 else heading
            chunks.append((label, buffer.strip()))

    if not chunks and (content or "").strip():
        chunks.append((None, content.strip()))
    return chunks
