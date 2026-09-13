import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  endLiveInterview,
  LiveInterviewStartResponse,
  startLiveInterview,
  submitLiveAnswer
} from "../api/interviews";
import { evaluateAnswer } from "../api/answers";
import { getJob, getLatestCandidateResume } from "../api/hr";
import { InterviewerAvatar } from "../components/InterviewerAvatar";

export function InterviewPage() {
  const [searchParams] = useSearchParams();
  // When launched from the pipeline, the interview is bound to a candidate and
  // requisition so its score feeds candidate ranking.
  const candidateIdParam = searchParams.get("candidate_id");
  const jobIdParam = searchParams.get("job_id");
  const candidateId = candidateIdParam ? Number(candidateIdParam) : undefined;
  const jobRequisitionId = jobIdParam ? Number(jobIdParam) : undefined;

  const [session, setSession] = useState<LiveInterviewStartResponse | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [persona, setPersona] = useState<"strict" | "friendly" | "stress">("friendly");
  const [targetRole, setTargetRole] = useState<string>("");
  const [resumeText, setResumeText] = useState("");
  const [prefillNote, setPrefillNote] = useState<string | null>(null);
  const [finalScore, setFinalScore] = useState<number | null>(null);
  const [transcript, setTranscript] = useState<
    {
      role: "assistant" | "user";
      content: string;
      relevance?: number;
    }[]
  >([]);

  // Prefill the resume text and role from the stored candidate/requisition
  // instead of asking the interviewer to paste a resume that is already parsed.
  useEffect(() => {
    if (candidateId === undefined) return;
    let cancelled = false;

    void (async () => {
      try {
        const resume = await getLatestCandidateResume(candidateId);
        if (!cancelled) {
          setResumeText(resume.extracted_text);
          setPrefillNote(
            `Loaded parsed resume for candidate #${candidateId} ` +
              `(${resume.extracted_text.length} characters, ${resume.extracted_skills.length} skills).`
          );
        }
      } catch {
        if (!cancelled) {
          setPrefillNote(
            `No parsed resume found for candidate #${candidateId}. Paste the resume text below.`
          );
        }
      }

      if (jobRequisitionId !== undefined) {
        try {
          const job = await getJob(jobRequisitionId);
          if (!cancelled) setTargetRole(job.title);
        } catch {
          // Leave the role empty so the interviewer can type it.
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [candidateId, jobRequisitionId]);

  async function handleStart(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const role = String(formData.get("targetRole") || "");
    const difficulty = (formData.get("difficulty") as "easy" | "medium" | "hard") || "medium";
    const personality =
      (formData.get("personality") as "strict" | "friendly" | "stress") || "friendly";

    setLoading(true);
    try {
      setPersona(personality);
      setTargetRole(role);
      const res = await startLiveInterview({
        resume_text: resumeText,
        target_role: role,
        difficulty,
        personality_mode: personality,
        candidate_id: candidateId,
        job_requisition_id: jobRequisitionId
      });
      setSession(res);
      setQuestion(res.first_question);
      setTranscript([{ role: "assistant", content: res.first_question }]);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitAnswer(e: FormEvent) {
    e.preventDefault();
    if (!session || !question) return;
    const currentAnswer = answer;
    const currentQuestion = question;
    setAnswer("");
    try {
      const pendingIndex = transcript.length;
      setTranscript((prev) => [...prev, { role: "user", content: currentAnswer }]);

      const [res, evalRes] = await Promise.all([
        submitLiveAnswer(session.id, currentAnswer),
        evaluateAnswer({ question: currentQuestion, answer: currentAnswer, target_role: targetRole })
          .catch(() => null)
      ]);

      if (evalRes?.relevance !== undefined) {
        setTranscript((prev) =>
          prev.map((m, idx) =>
            idx === pendingIndex ? { ...m, relevance: evalRes.relevance } : m
          )
        );
      }

      setQuestion(res.next_question);
      setSession({ ...session, question_index: res.question_index });
      setTranscript((prev) => [...prev, { role: "assistant", content: res.next_question }]);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async function handleEnd() {
    if (!session) return;
    try {
      // The backend scores the interview here and persists it, so the number
      // shown is the same one the candidate ranking will use.
      const result = await endLiveInterview(session.id);
      setFinalScore(result.overall_score ?? null);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setSession(null);
      setQuestion(null);
    }
  }

  return (
    <div className="layout">
      <div className="card" style={{ maxWidth: 980 }}>
        <div className="row space-between" style={{ alignItems: "flex-start", gap: 24 }}>
          <div style={{ flex: 1 }}>
            <h1 style={{ marginBottom: 4 }}>Live interview</h1>
            {session && (
              <span className={`chip ${persona}`}>
                Interviewer persona: <strong style={{ color: "#e5e7eb" }}>{persona}</strong>
              </span>
            )}
          </div>
          <div style={{ flexShrink: 0 }}>
            <InterviewerAvatar persona={persona} />
          </div>
        </div>

        {!session && finalScore !== null && (
          <div className="notice good">
            Interview scored {Math.round(finalScore)}/100 and saved
            {candidateId !== undefined ? " to the candidate record" : ""}.{" "}
            <Link to="/hr">View the updated ranking</Link>.
          </div>
        )}

        {!session && prefillNote && <div className="notice">{prefillNote}</div>}

        {!session && (
          <form onSubmit={handleStart} className="stack">
            <div className="input">
              <label htmlFor="targetRole">Target role</label>
              <input
                id="targetRole"
                name="targetRole"
                required
                placeholder="e.g. Backend Engineer"
                value={targetRole}
                onChange={(e) => setTargetRole(e.target.value)}
              />
            </div>
            <div className="row">
              <div className="input" style={{ flex: 1 }}>
                <label htmlFor="difficulty">Difficulty</label>
                <select id="difficulty" name="difficulty" defaultValue="medium">
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </div>
              <div className="input" style={{ flex: 1 }}>
                <label htmlFor="personality">Personality</label>
                <select id="personality" name="personality" defaultValue="friendly">
                  <option value="friendly">Friendly</option>
                  <option value="strict">Strict</option>
                  <option value="stress">Stress</option>
                </select>
              </div>
            </div>
            <div className="input">
              <label htmlFor="resumeText">
                Resume text {candidateId !== undefined ? "(loaded from the parsed resume)" : "(paste)"}
              </label>
              <textarea
                id="resumeText"
                name="resumeText"
                rows={6}
                placeholder="Paste resume text here to personalize the interview..."
                required
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
              />
            </div>
            <button className="btn" type="submit" disabled={loading}>
              {loading ? "Starting..." : "Start interview"}
            </button>
          </form>
        )}

        {session && (
          <div className="stack" style={{ marginTop: 24 }}>
            <div className="row space-between">
              <h2>Session #{session.id}</h2>
              <button className="btn secondary" type="button" onClick={handleEnd}>
                End interview
              </button>
            </div>

            {question && (
              <div className="chip" style={{ width: "fit-content" }}>
                Current question: <strong style={{ color: "#e5e7eb" }}>{question}</strong>
              </div>
            )}

            <div className="chat">
              {transcript.map((t, idx) => (
                <div key={idx} className={`bubble ${t.role}`}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>
                    {t.role === "assistant" ? "AI" : "You"}
                  </div>
                  <div>{t.content}</div>
                  {t.role === "user" && (
                    <div className="bubbleMeta">
                      <div className="row" style={{ gap: 10 }}>
                        <span>Relevance</span>
                        <div className="scoreBar" title={t.relevance ? `${t.relevance}/100` : ""}>
                          <div style={{ width: `${Math.max(0, Math.min(100, t.relevance ?? 0))}%` }} />
                        </div>
                        <span style={{ minWidth: 42, textAlign: "right" }}>
                          {t.relevance === undefined ? "—" : `${Math.round(t.relevance)}`}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {question && (
              <form onSubmit={handleSubmitAnswer} className="stack">
                <div className="input">
                  <label htmlFor="answer">Your answer</label>
                  <textarea
                    id="answer"
                    rows={4}
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    required
                  />
                </div>
                <button className="btn" type="submit" disabled={!answer.trim()}>
                  Send answer
                </button>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

