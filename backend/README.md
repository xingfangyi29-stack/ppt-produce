# Backend README

This is the FastAPI backend for the PPT Produce skeleton.

Setup (local):

1. Create and activate a Python virtual environment (recommended):

   python -m venv .venv
   source .venv/bin/activate   # macOS / Linux
   .venv\Scripts\activate     # Windows (PowerShell)

2. Install dependencies:

   pip install -r backend/requirements.txt

3. Start the server:

   # from repository root
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

   # or use the provided script
   bash backend/start.sh

The backend exposes a health endpoint at GET /api/health and a sample endpoint at /api/sample.
