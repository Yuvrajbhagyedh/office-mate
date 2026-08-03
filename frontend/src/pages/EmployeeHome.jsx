import React, { useState } from "react";
import ChatBox from "../components/ChatBox.jsx";
import { clearSession } from "../api.js";

const SUGGESTIONS = [
  "How many leave days do I get?",
  "What’s on the holiday list?",
  "Can I work from home?",
];

export default function EmployeeHome({ user, onLogout }) {
  const [draft, setDraft] = useState("");

  return (
    <div className="app employee-app">
      <div className="bg-wash employee-wash" aria-hidden="true" />
      <div className="orb orb-a" aria-hidden="true" />
      <div className="orb orb-b" aria-hidden="true" />

      <header className="topbar slim employee-top">
        <div className="user-chip">
          <span className="avatar" aria-hidden="true">
            {(user.name || "?").slice(0, 1)}
          </span>
          <div className="user-meta">
            <strong>{user.name}</strong>
            <span className="muted id-line">{user.employee_id}</span>
          </div>
        </div>
        <div className="top-actions">
          {user.role === "admin" && (
            <a className="text-link" href="#/admin">
              Admin
            </a>
          )}
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              clearSession();
              onLogout();
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="employee-main">
        <section className="hero">
          <p className="hero-eyebrow">
            <span className="pulse-dot" /> Office Mate
          </p>
          <h1 className="hero-title">
            Your office
            <br />
            <span className="hero-accent">mate</span> is here.
          </h1>
          <p className="hero-sub">
            Leave, holidays, HR rules — ask in plain English. Answers come only from company
            docs.
          </p>

          <div className="suggest-row">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" className="suggest-chip" onClick={() => setDraft(s)}>
                {s}
              </button>
            ))}
          </div>
        </section>

        <ChatBox
          documentCount={1}
          selected={[]}
          officeMode
          draft={draft}
          onDraftChange={setDraft}
        />
      </main>
    </div>
  );
}
