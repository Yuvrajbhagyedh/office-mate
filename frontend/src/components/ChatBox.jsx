import React, { useState } from "react";
import { api } from "../api.js";
import Citations from "./Citations.jsx";
import ContextInspector from "./ContextInspector.jsx";

function friendlyError(raw) {
  const msg = String(raw || "");
  const lower = msg.toLowerCase();
  if (
    lower.includes("503") ||
    lower.includes("high demand") ||
    lower.includes("unavailable") ||
    lower.includes("overloaded") ||
    lower.includes("busy") ||
    lower.includes("429") ||
    lower.includes("rate") ||
    lower.includes("try again")
  ) {
    return "The assistant is busy right now. Please try again in a moment.";
  }
  if (lower.includes("failed to fetch") || lower.includes("network")) {
    return "Couldn’t reach the server. Please try again.";
  }
  // Strip ugly JSON blobs from provider errors.
  if (lower.includes("google gemini") || lower.includes("query failed")) {
    return "Something went wrong answering that. Please try again.";
  }
  return msg.length > 160 ? "Something went wrong. Please try again." : msg;
}

function renderInline(text, keyPrefix) {
  // Split on [n] citations and **bold**
  const parts = text.split(/(\[\d+\]|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    if (/^\[\d+\]$/.test(part)) {
      return (
        <sup className="citemark" key={key}>
          {part}
        </sup>
      );
    }
    if (/^\*\*[^*]+\*\*$/.test(part)) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    return <span key={key}>{part}</span>;
  });
}

function AnswerText({ text }) {
  const lines = String(text || "")
    .replace(/\r\n/g, "\n")
    .trim()
    .split("\n");

  const blocks = [];
  let list = null;

  function flushList() {
    if (list?.length) {
      blocks.push({ type: "ul", items: list });
      list = null;
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      continue;
    }
    const bullet = trimmed.match(/^([-*•]|\d+\.)\s+(.*)$/);
    if (bullet) {
      list = list || [];
      list.push(bullet[2]);
      continue;
    }
    flushList();
    blocks.push({ type: "p", text: trimmed });
  }
  flushList();

  return (
    <div className="answerbody">
      {blocks.map((b, i) =>
        b.type === "ul" ? (
          <ul className="answerlist" key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{renderInline(item, `l${i}-${j}`)}</li>
            ))}
          </ul>
        ) : (
          <p className="answertext" key={i}>
            {renderInline(b.text, `p${i}`)}
          </p>
        )
      )}
    </div>
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
      setHistory((h) =>
        h.map((it) => (it === entry ? { question: q, error: friendlyError(err.message) } : it))
      );
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
            {it.loading && (
              <div className="a muted loading">Looking through your documents…</div>
            )}
            {it.error && (
              <div className="a error-box">
                <strong>Couldn’t answer that</strong>
                <p>{it.error}</p>
              </div>
            )}
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
