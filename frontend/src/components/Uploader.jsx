import React, { useRef, useState } from "react";
import { api } from "../api.js";

const ACCEPT = ".pdf,.docx,.txt,.md,.markdown";

export default function Uploader({ onUploaded }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  async function upload(file) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadDocument(file);
      onUploaded();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Library</h2>
        <p>PDF, DOCX, TXT, Markdown</p>
      </div>
      <div
        className={`dropzone ${dragOver ? "drag" : ""} ${busy ? "busy" : ""}`}
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          upload(e.dataTransfer.files[0]);
        }}
      >
        {busy ? (
          <div className="drop-copy">
            <strong>Indexing…</strong>
            <span>Extracting, chunking, embedding</span>
          </div>
        ) : (
          <div className="drop-copy">
            <strong>Drop a file</strong>
            <span>or click to browse</span>
          </div>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => upload(e.target.files[0])}
      />
      {error && <p className="error">{error}</p>}
    </section>
  );
}
