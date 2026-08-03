const TOKEN_KEY = "office_mate_token";
const USER_KEY = "office_mate_user";

// In production (Vercel), call Render directly so long /api/ask requests
// are not cut off by the Vercel rewrite proxy (which shows up as 502).
const API_BASE =
  import.meta.env.VITE_API_BASE ||
  (typeof window !== "undefined" && window.location.hostname.includes("vercel.app")
    ? "https://office-mate.onrender.com"
    : "");

function url(path) {
  return `${API_BASE}${path}`;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function handle(res) {
  if (res.status === 401) {
    clearSession();
    if (!location.hash.includes("login")) {
      location.hash = "#/login";
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
      }
    } catch {
      /* non-JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

function authHeaders(extra = {}) {
  const token = getToken();
  return {
    ...extra,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export const api = {
  login: (employeeId, dob) =>
    fetch(url("/api/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id: employeeId, dob }),
    }).then(handle),

  me: () => fetch(url("/api/auth/me"), { headers: authHeaders() }).then(handle),

  listDocuments: () => fetch(url("/api/documents"), { headers: authHeaders() }).then(handle),

  uploadDocument: (file) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(url("/api/documents"), {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }).then(handle);
  },

  deleteDocument: (id) =>
    fetch(url(`/api/documents/${id}`), {
      method: "DELETE",
      headers: authHeaders(),
    }).then(handle),

  ask: (question, documentIds) =>
    fetch(url("/api/ask"), {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        question,
        document_ids: documentIds && documentIds.length ? documentIds : null,
      }),
    }).then(handle),

  health: () => fetch(url("/health")).then(handle),
};
