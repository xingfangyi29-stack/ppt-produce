from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil
from .parser.ppt_parser import parse_pptx
from .ai.ai_service import generate_insights
from .ai.discussion_service import generate_discussion_areas
import uuid
import json

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
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


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
