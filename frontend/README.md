# BAPETEN AI Evaluator — React Frontend v0.2

Five separate pages controlled by the left sidebar, no infinite scrolling: Dashboard, Upload Dokumen, Formulir Permohonan, Hasil Matching and Dokumen.

**Start:** Node.js 20.19+ / 22.12+, `npm install && npm run dev`.
The local dev proxy routes `/api` to FastAPI on `http://127.0.0.1:8000` (see root `../README.md` for SSH forwarding and backend setup).

Workflow: select category, attach files; one PDF Formulir Permohonan and >=1 supporting document are required. Click **Mulai Analisis** on Upload. Enter the backend token in the top bar if required. The app uploads pending documents, creates job, polls progress, and renders only returned backend result. It shows per-document extraction errors and warnings. No demo data is shipped as analysis results.

Selected files live in browser memory until uploaded; server-saved metadata is restored with the current application ID after token reentry. Application ID is in sessionStorage, token only in memory. An ordinary refresh does not persist unsubmitted files. To start a new application use Dashboard > Permohonan Baru.

React source syntax was checked offline; npm registry could not be accessed in the current environment, so npm build and browser E2E must be checked on a machine with package access.

Before external exposure: implement institutional SSO, per-user access rights, PDF audit trails and retention. Current API token should only be used within an internal controlled network.
