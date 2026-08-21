from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil

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
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
