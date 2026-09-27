from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI(title="AI Company", version="1.0.0")


@app.get("/")
def home():
    index_file = Path(__file__).parent / "index.html"

    if index_file.exists():
        return HTMLResponse(
            index_file.read_text(encoding="utf-8")
        )

    return {
        "message": "AI Company is running"
    }


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "AI Company",
        "status": "online"
    }
