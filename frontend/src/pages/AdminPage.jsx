import React, { useCallback, useEffect, useState } from "react";
import { api, clearSession } from "../api.js";
import Uploader from "../components/Uploader.jsx";
import DocumentList from "../components/DocumentList.jsx";
import ChatBox from "../components/ChatBox.jsx";

export default function AdminPage({ user, onLogout }) {
  const [documents, setDocuments] = useState([]);
  const [selected, setSelected] = useState([]);
  const [health, setHealth] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [docs, h] = await Promise.all([api.listDocuments(), api.health()]);
      setDocuments(docs.documents);
      setHealth(h);
      setSelected((s) => s.filter((id) => docs.documents.some((d) => d.id === id)));
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggle = (id) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="app admin-app">
      <div className="bg-wash" aria-hidden="true" />

      <header className="topbar">
        <div className="brand-block">
          <div className="mark" aria-hidden="true" />
          <div>
            <div className="brand">Office Mate</div>
            <div className="brand-sub">Admin library</div>
          </div>
        </div>
        <div className="top-actions">
          <span className="user-chip muted">
            {user.name} · {user.employee_id}
          </span>
          {health && (
            <span className="health">
              <span className={`dot ${health.vector_store === "ok" ? "ok" : "bad"}`} />
              {health.documents} docs · {health.chunks} chunks
            </span>
          )}
          <a className="text-link" href="#/">
            Employee view
          </a>
          <button
            type="button"
            className="text-link"
            onClick={() => {
              clearSession();
              onLogout();
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <Uploader onUploaded={refresh} />
          <DocumentList
            documents={documents}
            selected={selected}
            onToggle={toggle}
            onChanged={refresh}
          />
        </aside>
        <section className="main">
          <ChatBox selected={selected} documentCount={documents.length} officeMode />
        </section>
      </main>
    </div>
  );
}
