from fastapi import FastAPI, UploadFile, File, HTTPException, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pathlib import Path
import shutil
from .parser.ppt_parser import parse_pptx
from .ai.ai_service import generate_insights
from .ai.discussion_service import generate_discussion_areas
from .ppt_generator.deck_generator import generate_deck
import uuid
import json
import os
from typing import Dict, Any, Optional

app = FastAPI(title="ppt-produce-backend")

# Allow local frontend dev origin
origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'uploads'
DRAFTS_DIR = UPLOAD_DIR / 'drafts'
GENERATED_DIR = UPLOAD_DIR / 'generated'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
async def health():
    return {"status":"ok"}


@app.get("/api/sample")
async def sample():
    return {"message":"sample endpoint — implement upload/analysis later"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    # Basic filename validation
    filename = Path(file.filename)
    if filename.suffix.lower() != '.pptx':
        raise HTTPException(status_code=400, detail="Only .pptx files are accepted")

    # Read a small chunk to validate ZIP magic header
    content = await file.read(4)
    await file.seek(0)
    if content[:2] != b'PK':
        raise HTTPException(status_code=400, detail="Invalid PPTX file (not a ZIP archive)")

    dest = UPLOAD_DIR / filename.name
    try:
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")
    finally:
        await file.close()

    size = dest.stat().st_size
    return {"success": True, "filename": filename.name, "size": size}


@app.post("/api/analyse")
async def analyse_file(file: UploadFile = File(...)):
    filename = Path(file.filename)
    if filename.suffix.lower() != '.pptx':
        raise HTTPException(status_code=400, detail="Only .pptx files are accepted")

    # basic zip header validation
    header = await file.read(4)
    await file.seek(0)
    if header[:2] != b'PK':
        raise HTTPException(status_code=400, detail="Invalid PPTX file (not a ZIP archive)")

    # write to a temp path
    dest = UPLOAD_DIR / (f"analyse_{filename.name}")
    try:
        with dest.open('wb') as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to store uploaded file for analysis")
    finally:
        await file.close()

    # call parser
    try:
        result = parse_pptx(str(dest))
    except Exception as e:
        # cleanup
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to parse PPTX: {e}")

    # generate AI insights and discussion areas (rule-based modules)
    try:
        insights = generate_insights(result)
        discussion = generate_discussion_areas(result)
        result['ai_insights'] = insights.get('insights', [])
        result['discussion_areas'] = discussion.get('discussion_areas', [])
    except Exception:
        # don't fail analysis if ai step has issues; include empty lists
        result['ai_insights'] = []
        result['discussion_areas'] = []

    # remove temp file
    try:
        dest.unlink(missing_ok=True)
    except Exception:
        pass

    return result


@app.post('/api/draft/save')
async def save_draft(draft: Dict = Body(...)):
    """Save an edited draft JSON server-side (temporary storage). Returns draft_id."""
    try:
        draft_id = str(uuid.uuid4())
        dest = DRAFTS_DIR / f"draft_{draft_id}.json"
        with dest.open('w', encoding='utf-8') as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
        return {"success": True, "draft_id": draft_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save draft: {e}")


@app.post('/api/generate')
async def generate_ppt(draft: Optional[Dict[str, Any]] = Body(None), draft_id: Optional[str] = None, background_tasks: BackgroundTasks = None):
    """
    Generate a PPTX from a draft payload or a saved draft_id and stream it back as a downloadable file.

    - If draft_id is provided, loads the draft from server-side storage.
    - Otherwise expects a draft JSON payload in the request body with keys parsed_readonly and edited.
    """
    if draft_id:
        path = DRAFTS_DIR / f"draft_{draft_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Draft not found")
        try:
            with path.open('r', encoding='utf-8') as f:
                draft = json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load draft: {e}")

    if not draft:
        raise HTTPException(status_code=400, detail="No draft provided")

    parsed = draft.get('parsed_readonly') or {}
    edited = draft.get('edited') or {}

    out_name = f"management_deck_{uuid.uuid4().hex[:8]}.pptx"
    out_path = GENERATED_DIR / out_name
    try:
        generate_deck(parsed, edited, str(out_path))
    except Exception as e:
        # ensure no partial file remains
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Deck generation failed: {e}")

    def file_iterator(path: Path):
        with path.open('rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk

    # cleanup task
    def _cleanup(path_str: str):
        try:
            os.remove(path_str)
        except Exception:
            pass

    if background_tasks is None:
        # instantiate one if not provided
        background_tasks = BackgroundTasks()
    background_tasks.add_task(_cleanup, str(out_path))

    headers = {"Content-Disposition": f"attachment; filename=management_deck.pptx"}
    return StreamingResponse(file_iterator(out_path), media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", headers=headers, background=background_tasks)
