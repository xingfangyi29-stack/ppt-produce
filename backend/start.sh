#!/usr/bin/env bash
# Start backend in development mode (assumes virtualenv and dependencies installed)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
