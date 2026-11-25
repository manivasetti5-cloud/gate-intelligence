# GATE Intelligence – AI-Powered Assessment Platform

A production-ready, database-driven GATE (Graduate Aptitude Test in Engineering) preparation, assessment, PDF ingestion, verification, and performance analytics platform supporting **CS**, **DA**, **EC**, **ME**, and **EE**.

## Core Capabilities

1. **Foundation & Multi-Branch Syllabus Hierarchy**
   - Student & Administrator roles with Argon2id password hashing, CSRF protection, RBAC, and audit logging.
   - Five official GATE branches (`CS`, `DA`, `EC`, `ME`, `EE`) with versioned syllabi (`Branch → Subject → Chapter → Topic → Concept`) and year-specific `ExamPattern`s.
2. **Examination Engine**
   - Four assessment modes: **Concept-Wise**, **Chapter-Wise**, **Subject-Wise**, and **Full-Length GATE Mock** (pattern-locked), plus **Daily Challenge** and **Reattempt Mode**.
   - Distraction-free CBT interface with countdown timer, 5-state question palette, debounced autosave, refresh recovery, server-side expiry auto-submit, and zero pre-submit answer leakage.
   - Official GATE scoring (`MCQ` negative marking `-1/3` and `-2/3`; `MSQ` and `NAT` zero negative marking), 8-part detailed solutions, Bookmarks, and automatic Error Notebook capture.
3. **Automatic PDF Extraction & AI Question Intelligence**
   - 9-step PDF upload pipeline: PyMuPDF / pure-Python `pypdf` extraction, OpenCV + Tesseract OCR fallback, question segmentation, diagram preservation, syllabus classification, AI solving, independent verification (SymPy + second LLM pass), and duplicate detection (SHA-256 + TF-IDF + perceptual image dHash).
   - Original syllabus-aligned AI question generator gated behind strict JSON schema checks and independent verification before publication.
   - Strict source provenance (`PYQ` and `AI_GENERATED`). No fake or demo questions are seeded.
4. **Analytics, Readiness & AI Advisor**
   - Longitudinal performance dashboards (Chart.js), speed & rapid-guessing diagnostics, internal GATE Readiness Tracker, searchable **Formula & Shortcut Library** (50+ GATE identities across all 5 branches & General Aptitude), 10-point AI Preparation Advisor, and editable 7-Day Revision Plans.

---

## Cloud Database & Zero-Local-Storage Deployment (Open-Source Stack)

You do **not** need to run or store a local PostgreSQL database on your computer. Use a free open-source cloud PostgreSQL provider:

- **[Neon](https://neon.tech)** (open-source serverless Postgres, free tier)
- **[Supabase](https://supabase.com)** (open-source Postgres platform, free tier)

1. Create a free project on Neon or Supabase and copy its connection URI:
   ```text
   postgresql://USER:PASSWORD@HOST:5432/DB_NAME?sslmode=require
   ```
   *(The app automatically normalizes `postgres://` and `postgresql://` URIs to `postgresql+psycopg://`.)*

2. **One-Click / Free Cloud Deployment on [Render](https://render.com)**:
   - Push this repository to GitHub.
   - In Render, choose **New + → Blueprint** (uses [render.yaml](file:///d:/work/gate%20app/render.yaml)) or **New Web Service**.
   - Set environment variables:
     - `DATABASE_URL` = your Neon or Supabase connection string
     - `DEFAULT_ADMIN_PASSWORD` = a strong admin password
     - `GEMINI_API_KEY` = *(optional)* your Gemini API key for live AI solving & question generation
   - Render runs `python -m flask db upgrade && python -m flask seed` automatically and serves the app with **Gunicorn** (health check at `/health`).

3. **Docker Deployment**:
   ```bash
   cp .env.example .env
   # Put your Neon/Supabase DATABASE_URL in .env
   docker compose up --build -d
   ```

---

## Importing Real Open-Source GATE Question Papers (PYQs)

Instead of fake demo items, ingest real historical GATE papers from open-source archives:
- Official GATE PDF collections: `gadepall/GATE`, `GATEOverflow/GO-PDFs`, `DS-AI-GATE/dsai-gate` (GitHub)

**Option A – Admin Web UI:** Log in at `/auth/admin/login` → **Paper Upload** (`/admin/upload-paper`), select branch and year, and upload any GATE PDF.

**Option B – Bulk CLI Importer:**
```bash
python -m scripts.import_open_source_papers --dir ./pdfs/cs_2024 --branch CS --year 2024
```

**Option C – Authorized JSON Dataset Importer:**
```bash
python -m scripts.import_historical_papers --file path/to/authorized_pyqs.json
```

---

## Local Development & Running Tests

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
python -m pip install -r requirements.txt
cp .env.example .env
```

Run automated tests (uses fast in-memory DB when `TEST_DATABASE_URL` is blank, or any PostgreSQL test DB when set):
```bash
python -m pytest -v
```

Run locally:
```bash
python -m flask db upgrade
python -m flask seed
python run.py
```
