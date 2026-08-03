import React, { useState } from "react";
import { api } from "../api.js";
import Citations from "./Citations.jsx";
import ContextInspector from "./ContextInspector.jsx";

function AnswerText({ text }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="answertext">
      {parts.map((p, i) =>
        /^\[\d+\]$/.test(p) ? (
          <sup className="citemark" key={i}>
            {p}
          </sup>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </p>
  );
}

export default function ChatBox({
  selected,
  documentCount,
  officeMode,
  draft,
  onDraftChange,
}) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);

  const value = draft != null ? draft : question;
  const setValue = onDraftChange || setQuestion;

  async function ask(e) {
    e.preventDefault();
    const q = value.trim();
    if (!q || busy) return;
    setBusy(true);
    setValue("");
    const entry = { question: q, loading: true };
    setHistory((h) => [entry, ...h]);
    try {
      const response = await api.ask(q, selected);
      setHistory((h) => h.map((it) => (it === entry ? { question: q, response } : it)));
    } catch (err) {
      setHistory((h) => h.map((it) => (it === entry ? { question: q, error: err.message } : it)));
    } finally {
      setBusy(false);
    }
  }

  const canAsk = officeMode ? true : !!documentCount;

  return (
    <section className={`panel chat ${officeMode ? "chat-hero" : ""}`}>
      {!officeMode && (
        <div className="panel-head">
          <h2>Ask</h2>
          <p>
            {documentCount
              ? selected.length
                ? `Scoped to ${selected.length} selected document${selected.length > 1 ? "s" : ""}`
                : "Searching all indexed documents"
              : "Upload a document before asking"}
          </p>
        </div>
      )}

      <form onSubmit={ask} className="askform">
        <input
          type="text"
          value={value}
          placeholder={
            officeMode
              ? "Ask about leave, holidays, WFH…"
              : documentCount
                ? "Ask a question about your documents…"
                : "Upload a document first…"
          }
          onChange={(e) => setValue(e.target.value)}
          disabled={busy || !canAsk}
        />
        <button type="submit" disabled={busy || !canAsk || !value.trim()}>
          {busy ? "…" : "Ask"}
        </button>
      </form>

      <div className="history">
        {!history.length && !officeMode && (
          <div className="empty chat-empty">
            Try: “How many leave days do I get?” or “What’s the holiday list?”
          </div>
        )}

        {history.map((it, idx) => (
          <article className="qa" key={idx}>
            <div className="q">{it.question}</div>
            {it.loading && <div className="a muted loading">Retrieving · reranking · generating</div>}
            {it.error && <div className="a error-box">{it.error}</div>}
            {it.response && (
              <div className={`a ${it.response.grounded ? "" : "ungrounded"}`}>
                {!it.response.grounded && (
                  <div className="refusal">No supporting evidence found</div>
                )}
                <AnswerText text={it.response.answer} />
                <Citations citations={it.response.citations} />
                <ContextInspector
                  chunks={it.response.retrieved_context}
                  timings={it.response.timings_ms}
                />
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
