import { FormEvent, useState } from "react";
import {
  endLiveInterview,
  LiveInterviewStartResponse,
  startLiveInterview,
  submitLiveAnswer
} from "../api/interviews";
import { evaluateAnswer } from "../api/answers";
import { InterviewerAvatar } from "../components/InterviewerAvatar";

export function InterviewPage() {
  const [session, setSession] = useState<LiveInterviewStartResponse | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [persona, setPersona] = useState<"strict" | "friendly" | "stress">("friendly");
  const [targetRole, setTargetRole] = useState<string>("");
  const [transcript, setTranscript] = useState<
    {
      role: "assistant" | "user";
      content: string;
      relevance?: number;
    }[]
  >([]);

  async function handleStart(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const role = String(formData.get("targetRole") || "");
    const difficulty = (formData.get("difficulty") as "easy" | "medium" | "hard") || "medium";
    const personality =
      (formData.get("personality") as "strict" | "friendly" | "stress") || "friendly";
    const resumeText = String(formData.get("resumeText") || "");

    setLoading(true);
    try {
      setPersona(personality);
      setTargetRole(role);
      const res = await startLiveInterview({
        resume_text: resumeText,
        target_role: role,
        difficulty,
        personality_mode: personality
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
      await endLiveInterview(session.id);
    } catch {
      // ignore errors for now
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

        {!session && (
          <form onSubmit={handleStart} className="stack">
            <div className="input">
              <label htmlFor="targetRole">Target role</label>
              <input id="targetRole" name="targetRole" required placeholder="e.g. Backend Engineer" />
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
              <label htmlFor="resumeText">Resume text (paste)</label>
              <textarea
                id="resumeText"
                name="resumeText"
                rows={6}
                placeholder="Paste your resume text here to personalize the interview..."
                required
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

