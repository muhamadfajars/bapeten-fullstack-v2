# BAPETEN AI Evaluator — Frontend + FastAPI v0.2

This is a **working local/intranet integration candidate**, not a certified 100%-production-ready system. It contains a React TypeScript interface and a backend executing the original v46 BAPETEN extraction/matching modules. It is not a replacement for regulatory review.

## Pages

The left menu switches between five independent pages (other pages are hidden): **Dashboard**, **Upload Dokumen**, **Formulir Permohonan**, **Hasil Matching**, and **Dokumen**. Upload a single PDF application form and supporting files, then click **Mulai Analisis** in Upload. The frontend submits all pending files to the API, polls the job, and displays real backend results, per-document errors, and evidence source pages. No demo matching is displayed as real data.


## Single-command HPC launch (port 8001; recommended for internal pilot)

This package additionally contains four root-level executable shell scripts. The frontend is
built **once** and served by FastAPI at the **same origin**, so **no second Vite process or
port 5173** is needed on the HPC after build. Your previous Streamlit port 8501 is untouched.

```bash
cd ~/bapeten-fullstack-v2
bash setup_bapeten_fullstack.sh          # once: pip + npm + build + private token
bash start_bapeten_fullstack.sh          # each start, daemon/background
bash status_bapeten_fullstack.sh
# when needed:
bash stop_bapeten_fullstack.sh
```

The setup needs Python >=3.10, Node.js >=20, npm and access to package dependencies.
For an existing OCR-enabled Python venv, you can provide an explicit interpreter path:
`BAPETEN_PYTHON=/absolute/path/to/venv/bin/python bash setup_bapeten_fullstack.sh`
and use the same `BAPETEN_PYTHON` when starting. Test PaddleOCR/PaddlePaddle and any
Tesseract models in the selected environment; **pip installing the requirements.txt alone
does not install/guarantee every OCR model**. If HPC cannot access npm registry, build
`frontend/dist` on a trusted developer machine and copy that directory onto the HPC,
then set up Python manually (see old instructions below).

On the user's machine open an SSH tunnel and browse **one** forwarded port:

```bash
ssh -L 8001:127.0.0.1:8001 USER@HPC_HOST
```

Then open `http://localhost:8001`. API and frontend share that port.
`backend/.env` is generated only if absent; it stores the persistent private access token
and data folder. Keep permissions at `0600` and never share its content. To view it
locally on the HPC: `grep '^BAPETEN_API_TOKEN=' backend/.env`. Logs are written to
`logs/bapeten-fullstack.log`; PID to `run/bapeten-fullstack.pid`. No Streamlit files are
modified. The launcher is intentionally bound only to `127.0.0.1`; for multi-user
production deploy use an approved authentication/TLS/reverse-proxy solution.

---
## 1. Install backend on the same HPC where Python OCR works

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# IMPORTANT: keep existing working PaddleOCR, PaddlePaddle, Tesseract, system libraries,
# and GPU/CPU configuration on the HPC. Install missing OCR engine dependencies there.
export BAPETEN_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(40))')"
export BAPETEN_DATA_DIR="$HOME/bapeten-private-data"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Keep the generated token in a safe place; enter it in the web frontend **API Token** field. The API refuses most requests without a configured token. It binds to loopback by default. SQLite stores metadata and serialized job results; uploaded binary files are saved in a private directory. Never place this directory under a public static/web root. No medical files are included in the source ZIP.

For Tesseract scanned documents you need the `tesseract-ocr` executable plus appropriate Indonesian/English language packs. OCR for labels and certain documents additionally requires PaddleOCR/PaddlePaddle and compatible local models already used by the v46 engine. This source package does not bundle proprietary models.

## 2. Install React frontend (Windows / Linux)

Install Node.js >=20, then:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite proxy forwards `/api` to **localhost:8000**. If the Python backend runs on your HPC, open SSH port forwarding in another local terminal:

```bash
ssh -L 8000:127.0.0.1:8000 <ssh-user>@<hpc-host>
```

Replace placeholders with your real SSH configuration. Enter the backend token in the frontend field after opening the app.

Production build (on a machine that can download npm dependencies):

```bash
cd frontend
npm run build
```

Deploy `frontend/dist/` as static files through Nginx, proxy `/api/` to `http://127.0.0.1:8000/api/`, enforce TLS, internal-network restriction, RBAC/authentication, logging policy, encryption at rest, resource limits, retention, malware scan, backups, and security review.

## 3. Test backend

```bash
cd backend
python -m compileall -q app engine/src
python -m unittest discover -s tests -p 'test_api.py' -v
```

The test creates a synthetic *form* and uploads a synthetic multi-page maintenance PDF for a fictionalized regression flow. The bundled `tests/test_api.py` generates synthetic form and maintenance PDFs in memory, so it runs without distributing original hospital documents. For fixture-free smoke validation:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## Implemented backend API

- `POST /api/v1/applications` — create opaque application ID
- `GET /api/v1/applications/{id}/documents` — list uploads
- `POST /api/v1/applications/{id}/documents` — multipart file, category, optional subtype
- `DELETE /api/v1/applications/{id}/documents/{document_id}` — remove upload
- `GET /api/v1/applications/{id}/documents/{document_id}/file` — authenticated raw source
- `POST /api/v1/applications/{id}/analyses` — run analysis in worker thread
- `GET /api/v1/applications/{id}/jobs/{job_id}` — poll status/progress/failure
- `GET /api/v1/applications/{id}/results` — latest completed result and per-document failures

All except `/api/v1/health` require `Authorization: Bearer <token>` unless explicitly overridden **for local development only**.

## Important limits before actual operational deployment

1. **Single-workspace API token**, not full per-evaluator accounts, roles, or document-level authorization. Do not expose on the public internet. Implement institution SSO and audit logs before production.
2. **Threaded worker**, not durable Redis/RQ/Celery. Jobs can be interrupted by process restarts, and concurrency requires validation on the actual HPC. Run only one Uvicorn worker unless replacing this job model with a durable queue.
3. **Matching is evidence-first**. An unrecognized document, OCR failure, missing form data or unsupported file type produces an explicit error/REVIEW, never synthetic MATCH. Category-specific robustness is inherited from the baseline v46, including its known limitations.
4. **No front-end build in current source-creation environment** due unavailable npm registry dependencies. TypeScript/TSX syntax was checked with the global TypeScript compiler, but you must run `npm install`, `npm run build`, and browser E2E tests on a network-connected developer machine.
5. **Data handling**: Files may contain personal/clinical/regulatory data. Obtain approval for deployment, set quotas, TLS, secure storage, access policy, encryption, file retention, backup, incident monitoring, and penetration testing.
6. **Persistence and sessions**: The client stores only opaque application ID in `sessionStorage`; entered API token stays in volatile React state. A browser refresh requires entering the token again. The app attempts to restore previous uploaded file metadata and latest **matching-fingerprint-consistent** result after authorization.

## Package layout

- `frontend/`: source-only React + Vite app
- `backend/app/`: authenticated REST endpoints, SQLite metadata, threaded job orchestration, engine adapter
- `backend/engine/src/`: original source modules from provided baseline plus v43, v44, and v46 patch modules
- `backend/tests/`: API integration tests (test fixture path is environment-specific)
- `deploy/`: minimal internal Nginx template

No Streamlit app is modified. Keep the existing Streamlit instance as a fallback until the HPC acceptance tests pass.
