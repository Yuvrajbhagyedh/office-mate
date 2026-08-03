import React from "react";
import { api } from "../api.js";

function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function DocumentList({ documents, selected, onToggle, onChanged }) {
  async function remove(id, e) {
    e.stopPropagation();
    await api.deleteDocument(id);
    onChanged();
  }

  return (
    <section className="panel grow">
      <div className="panel-head">
        <h2>Documents</h2>
        <p>
          {documents.length
            ? "Select to scope a question. None selected searches all."
            : "Upload a document to get started."}
        </p>
      </div>

      {!documents.length ? (
        <div className="empty">No documents yet</div>
      ) : (
        <ul className="doclist">
          {documents.map((d) => {
            const active = selected.includes(d.id);
            return (
              <li
                key={d.id}
                className={`docitem ${active ? "sel" : ""} ${d.status !== "ready" ? "disabled" : ""}`}
                onClick={() => d.status === "ready" && onToggle(d.id)}
              >
                <div className="doc-check" aria-hidden="true">
                  <span className={active ? "checked" : ""} />
                </div>
                <div className="doc-body">
                  <div className="docname">{d.filename}</div>
                  <div className="docmeta">
                    {d.filetype.toUpperCase()} · {fmtBytes(d.size_bytes)} · {d.num_chunks} chunks
                  </div>
                  {d.error && <div className="error">{d.error}</div>}
                </div>
                <div className="doc-actions">
                  <span className={`badge ${d.status}`}>{d.status}</span>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={(e) => remove(d.id, e)}
                    title="Delete"
                    aria-label={`Delete ${d.filename}`}
                  >
                    ×
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
