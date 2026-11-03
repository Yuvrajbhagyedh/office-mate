import React, { useEffect, useState } from "react";
import { api, setSession } from "../api.js";

// Free-tier Render sleeps after ~15 min idle; the first request then takes
// 30-60s to wake it. Pinging /health as soon as the login page loads starts
// that wake-up during typing instead of after Continue is clicked.
const WAKING_HINT_DELAY_MS = 4000;

export default function LoginPage({ onLoggedIn }) {
  const [employeeId, setEmployeeId] = useState("");
  const [dob, setDob] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    let settled = false;
    const hintTimer = setTimeout(() => {
      if (!settled) setWaking(true);
    }, WAKING_HINT_DELAY_MS);
    api
      .health()
      .catch(() => {})
      .finally(() => {
        settled = true;
        setWaking(false);
      });
    return () => clearTimeout(hintTimer);
  }, []);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(employeeId.trim(), dob.trim());
      const user = {
        employee_id: res.employee_id,
        name: res.name,
        role: res.role,
      };
      setSession(res.access_token, user);
      onLoggedIn(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="bg-wash" aria-hidden="true" />
      <div className="login-card">
        <p className="login-eyebrow">Sign in</p>
        <h1 className="login-title">Office Mate</h1>
        <p className="login-sub">Use your employee ID and date of birth to continue.</p>

        <form className="login-form" onSubmit={submit}>
          <label>
            <span>Employee ID</span>
            <input
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="e.g. EMP1001"
              autoComplete="username"
              required
            />
          </label>
          <label>
            <span>Date of birth</span>
            <input
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              required
            />
          </label>
          {waking && !error && (
            <p className="login-waking">Waking up the server — first sign-in can take up to a minute.</p>
          )}
          {error && <p className="error-box">{error}</p>}
          <button type="submit" disabled={busy || !employeeId.trim() || !dob}>
            {busy ? "Signing in…" : "Continue"}
          </button>
        </form>

        <div className="login-hint">
          <p>Demo employee — ID <code>EMP1001</code> · DOB <code>1995-06-20</code></p>
          <p>Demo admin — ID <code>ADMIN001</code> · DOB <code>1990-01-15</code></p>
        </div>
      </div>
    </div>
  );
}
