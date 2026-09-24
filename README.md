# ReleaseGuard v0.1

ReleaseGuard is a developer reliability platform for:
- capturing application errors
- grouping duplicate failures into issues
- tracking releases
- later: deterministic feature flags, multi-tenancy, mitigation, and AI incident assistance

## First invariant

> 1,000 identical error events should become 1 issue with count=1,000.

## v0.1 scope

This first version intentionally builds only the smallest vertical slice:

Project -> Error Event -> Fingerprint -> Issue -> Dashboard/API

SQLite is used only for the first development slice so the system stays lightweight on an 8 GB laptop.
We will move the core persistence to PostgreSQL before we tackle real concurrency, tenant isolation, and production-grade guarantees.

## Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/health
