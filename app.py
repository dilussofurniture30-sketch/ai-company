import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="AI Company", version="1.0.1")

DB_PATH = os.getenv("DATABASE_PATH", "./data/company.db")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


# =========================
# DATABASE
# =========================

def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = db()

    connection.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT,
        task TEXT,
        status TEXT,
        budget REAL DEFAULT 0,
        revenue REAL DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT,
        agent TEXT,
        event_type TEXT,
        message TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        action TEXT,
        status TEXT,
        created_at TEXT
    );
    """)

    connection.commit()
    connection.close()


init_db()


# =========================
# MODELS
# =========================

class ChatIn(BaseModel):
    message: str
    project_id: Optional[str] = None


class ApprovalIn(BaseModel):
    project_id: str
    action: str


class ResearchIn(BaseModel):
    task: str


# =========================
# HELPERS
# =========================

def create_project(task):
    project_id = str(uuid.uuid4())

    connection = db()

    connection.execute(
        """
        INSERT INTO projects
        (id, name, task, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            project_id,
            task[:80],
            task,
            "running",
            datetime.now(timezone.utc).isoformat()
        )
    )

    connection.commit()
    connection.close()

    return project_id


def log_event(project_id, agent, event_type, message):
    connection = db()

    connection.execute(
        """
        INSERT INTO events
        (project_id, agent, event_type, message, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            project_id,
            agent,
            event_type,
            message,
            datetime.now(timezone.utc).isoformat()
        )
    )

    connection.commit()
    connection.close()


# =========================
# HOME
# =========================

@app.get("/", response_class=HTMLResponse)
def home():
    index_file = Path(__file__).parent / "index.html"

    if index_file.exists():
        return HTMLResponse(
            index_file.read_text(encoding="utf-8")
        )

    return HTMLResponse(
        "<h1>AI Company is Online</h1>"
    )


# =========================
# HEALTH
# =========================

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "AI Company",
        "status": "online"
    }


# =========================
# CHAT
# =========================

@app.post("/api/chat")
async def chat(body: ChatIn):

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured."
        )

    from agents import Agent, Runner

    manager = Agent(
        name="Manager",
        instructions="""
        You are the Manager of an AI service company.
        Understand the user's request, create a plan,
        and provide a clear useful response.
        Never claim an external action was completed
        unless it actually happened.
        """
    )

    project_id = body.project_id

    if not project_id:
        project_id = create_project(body.message)

    log_event(
        project_id,
        "Manager",
        "request",
        body.message
    )

    result = await Runner.run(
        manager,
        body.message
    )

    output = result.final_output

    log_event(
        project_id,
        "Manager",
        "response",
        output
    )

    return {
        "project_id": project_id,
        "response": output
    }


# =========================
# RESEARCH
# =========================

@app.post("/api/research")
async def research(body: ResearchIn):

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured."
        )

    from agents import Agent, Runner, WebSearchTool

    researcher = Agent(
        name="Researcher",
        instructions="""
        Perform web research using live search.
        Never invent facts or URLs.
        Clearly identify uncertain information.
        Provide sources for important claims.
        """,
        tools=[
            WebSearchTool(
                search_context_size="high",
                external_web_access=True
            )
        ]
    )

    project_id = create_project(body.task)

    log_event(
        project_id,
        "Researcher",
        "start",
        body.task
    )

    result = await Runner.run(
        researcher,
        body.task
    )

    output = result.final_output

    log_event(
        project_id,
        "Researcher",
        "result",
        output
    )

    connection = db()

    connection.execute(
        "UPDATE projects SET status=? WHERE id=?",
        ("completed", project_id)
    )

    connection.commit()
    connection.close()

    return {
        "project_id": project_id,
        "research": output
    }


# =========================
# APPROVALS
# =========================

@app.post("/api/approvals")
def approval(body: ApprovalIn):

    approval_id = str(uuid.uuid4())

    connection = db()

    connection.execute(
        """
        INSERT INTO approvals
        (id, project_id, action, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            approval_id,
            body.project_id,
            body.action,
            "pending",
            datetime.now(timezone.utc).isoformat()
        )
    )

    connection.commit()
    connection.close()

    return {
        "approval_id": approval_id,
        "status": "pending",
        "message": "Human approval required."
    }


# =========================
# PROJECTS
# =========================

@app.get("/api/projects")
def projects():

    connection = db()

    rows = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
    ]

    connection.close()

    return rows


# =========================
# EVENTS
# =========================

@app.get("/api/events/{project_id}")
def events(project_id: str):

    connection = db()

    rows = [
        dict(row)
        for row in connection.execute(
            """
            SELECT *
            FROM events
            WHERE project_id=?
            ORDER BY id
            """,
            (project_id,)
        ).fetchall()
    ]

    connection.close()

    return rows
