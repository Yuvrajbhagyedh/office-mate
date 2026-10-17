# Host Office Mate online (free)

Your code is already on GitHub:
https://github.com/Yuvrajbhagyedh/office-mate

Do **not** upload `backend/.env`. Put secrets only in the host dashboard.

---

## Step 1 — Backend on Render (free)

1. Go to https://render.com → Sign up with GitHub  
2. **New → Web Service** → select `office-mate`  
3. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Docker (uses `backend/Dockerfile`)
   - **Instance:** Free
4. **Environment** (Add Environment Variable):

| Key | Value |
|-----|--------|
| `GOOGLE_API_KEY` | your real Google AI Studio key |
| `LLM_PROVIDER` | `google` |
| `LLM_MODEL` | `gemini-flash-latest` |
| `AUTH_SECRET` | any long random string (required — the default is public) |
| `ENVIRONMENT` | `production` |
| `QDRANT_LOCAL_PATH` | `./data/qdrant` |
| `CORS_ORIGINS` | `["https://YOUR-VERCEL-URL.vercel.app"]` (update after Step 2) |

5. Click **Create Web Service** and wait for deploy  
6. Copy your URL, e.g. `https://office-mate-xxxx.onrender.com`

Free Render sleeps when idle — first open after a while can take ~30–60s.

---

## Step 2 — Point frontend at that backend

1. On your PC, open `frontend/vercel.json`  
2. Replace **both** `REPLACE_WITH_RENDER_URL` with your Render URL (**no trailing slash**), e.g.:

```json
"destination": "https://office-mate-xxxx.onrender.com/api/$1"
```

3. Commit and push:

```powershell
cd C:\rag-app
git add frontend/vercel.json
git commit -m "Point Vercel rewrites to Render backend"
git push
```

---

## Step 3 — Frontend on Vercel (free)

1. Go to https://vercel.com → Sign up with GitHub  
2. **Add New Project** → import `office-mate`  
3. Settings:
   - **Root Directory:** `frontend`
   - **Framework:** Vite (auto)
   - Build: `npm run build` · Output: `dist`
4. Deploy  
5. Copy your Vercel URL, e.g. `https://office-mate.vercel.app`

---

## Step 4 — Fix CORS

1. Back on Render → Environment  
2. Set `CORS_ORIGINS` to:

```text
["https://office-mate.vercel.app"]
```

(use your real Vercel URL)  
3. Save → Render redeploys  

---

## Step 5 — Try it

Open the Vercel URL:

| Role | Employee ID | DOB |
|------|-------------|-----|
| Employee | `EMP1001` | `1995-06-20` |
| Admin | `ADMIN001` | `1990-01-15` |

Employees ask leave/HR questions. The site starts with the documents in
`backend/seed_docs/` already loaded (see below).

---

## Keeping documents on the free plan

Render's free plan has **no persistent disk**: every restart or redeploy wipes
`backend/data/`, including documents an admin uploaded.

- **Permanent documents:** put them in `backend/seed_docs/` and push. Whenever
  the server starts with an empty database it loads every PDF, DOCX, TXT and
  Markdown file in that folder. Replace `sample_hr_policy.md` with your real
  policies.
- **Admin uploads** still last only until the next restart. To keep them, use
  a paid Render disk mounted at `/app/data`, or move storage off the
  container (Qdrant Cloud free tier via `QDRANT_URL` + `QDRANT_API_KEY`, and a
  hosted database instead of SQLite).

## Keeping the backend awake

Render's free plan sleeps after ~15 minutes idle, and the next request takes
about 30 seconds. `.github/workflows/keep-warm.yml` pings `/health` every 10
minutes. If your backend URL is not `https://office-mate.onrender.com`, set a
repository variable `BACKEND_URL` (GitHub → Settings → Secrets and variables →
Actions → Variables). GitHub pauses scheduled workflows after 60 days without
repo activity; re-enable it from the Actions tab.

---

## If something fails

- **API errors / CORS** → check `CORS_ORIGINS` matches Vercel exactly (`https`, no slash)  
- **401 on ask** → log in again  
- **Slow first load** → Render free tier waking up (see "Keeping the backend awake")  
- **Every answer says the documents don't contain the answer** → check `/health`
  shows documents > 0; if not, add files to `backend/seed_docs/`  
- **Blank page** → confirm Vercel Root Directory is `frontend`
