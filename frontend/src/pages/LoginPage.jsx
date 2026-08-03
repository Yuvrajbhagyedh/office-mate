import React, { useState } from "react";
import { api, setSession } from "../api.js";

export default function LoginPage({ onLoggedIn }) {
  const [employeeId, setEmployeeId] = useState("");
  const [dob, setDob] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

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
