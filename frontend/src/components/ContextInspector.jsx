import React, { useState } from "react";

export default function ContextInspector({ chunks, timings }) {
  const [open, setOpen] = useState(false);
  if (!chunks || !chunks.length) return null;

  const fmt = (n) => (n == null ? "—" : Number(n).toFixed(3));

  return (
    <div className="inspector">
      <button type="button" className="inspector-toggle" onClick={() => setOpen((o) => !o)}>
        <span>{open ? "Hide context" : "Show retrieved context"}</span>
        <span className="muted">
          {chunks.length} chunks
          {timings &&
            ` · ${Math.round(timings.total ?? 0)} ms total`}
        </span>
      </button>
      {open && (
        <div className="chunks">
          {timings && (
            <div className="timing-row muted">
              retrieval {Math.round(timings.vector_search ?? 0)} ms · rerank{" "}
              {Math.round(timings.rerank ?? 0)} ms · llm {Math.round(timings.llm ?? 0)} ms
            </div>
          )}
          {chunks.map((c, i) => (
            <div className="chunk" key={c.chunk_id}>
              <div className="chunkhead">
                <b>#{i + 1}</b> {c.filename}
                {c.page != null && <span className="muted"> · p. {c.page}</span>}
                {c.section && <span className="muted"> · {c.section}</span>}
              </div>
              <div className="scores muted">
                rerank {fmt(c.rerank_score)} · fused {fmt(c.fused_score)} · vector{" "}
                {fmt(c.vector_score)} · bm25 {fmt(c.bm25_score)}
              </div>
              <p className="chunktext">{c.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
