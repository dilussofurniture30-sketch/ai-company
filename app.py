import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agents import Agent, Runner, WebSearchTool

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "./data/company.db")
MODEL = os.getenv("OPENAI_MODEL") or None
MAX_RETRIES = int(os.getenv("MAX_AGENT_RETRIES", "2"))

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AI Company",
    version="1.0.0"
)


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
    CREATE TABLE IF NOT EXISTS projects(
        id TEXT PRIMARY KEY,
        name TEXT,
        task TEXT,
        status TEXT,
        budget REAL DEFAULT 0,
        revenue REAL DEFAULT 0,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT,
        agent TEXT,
        event_type TEXT,
        message TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS approvals(
        id TEXT PRIMARY KEY,
        project_id TEXT,
        action TEXT,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS opportunities(
        id TEXT PRIMARY KEY,
        title TEXT,
        source TEXT,
        url TEXT,
        price REAL DEFAULT 0,
        estimated_cost REAL DEFAULT 0,
        estimated_profit REAL DEFAULT 0,
        risk TEXT,
        raw TEXT,
        created_at TEXT
    );
    """)

    connection.commit()
    connection.close()


init_db()


# =========================
# HELPERS
# =========================

def log(project_id, agent, event_type, message):
    connection = db()

    connection.execute(
        """
        INSERT INTO events(
            project_id,
            agent,
            event_type,
            message,
            created_at
        )
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


def new_project(task, budget=0, revenue=0):
    project_id = str(uuid.uuid4())

    connection = db()

    connection.execute(
        """
        INSERT INTO projects
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            task[:80],
            task,
            "running",
            budget,
            revenue,
            datetime.now(timezone.utc).isoformat()
        )
    )

    connection.commit()
    connection.close()

    return project_id


def make_agent(name, instructions, tools=None):

    kwargs = {
        "name": name,
        "instructions": instructions
    }

    if MODEL:
        kwargs["model"] = MODEL

    if tools:
        kwargs["tools"] = tools

    return Agent(**kwargs)


# =========================
# TOOLS
# =========================

web = WebSearchTool(
    search_context_size="high"
)


# =========================
# AI EMPLOYEES
# =========================

manager = make_agent(
    "Manager",
    """
You are the CEO and Project Manager of an AI service company.

Break tasks into explicit steps.
Assign work to specialists.
Define acceptance criteria.
Monitor quality and budget.

Never claim an external action was completed unless it actually happened.

External submissions, contracts, payments,
account changes and irreversible actions require human approval.
"""
)


job_hunter = make_agent(
    "Job Hunter",
    """
Find current public freelance opportunities using live web research.

Never fabricate jobs.

Return:
- title
- source
- URL
- buyer requirements
- apparent budget
- deadline if available
- required skills
- evidence URL

Do not submit applications.
Do not contact buyers.
Respect marketplace terms.
""",
    [web]
)


analyst = make_agent(
    "Opportunity Analyst",
    """
Analyze freelance opportunities.

Estimate:
- effort
- AI/tool cost
- human review cost
- platform fees
- risk
- contribution margin

Clearly state assumptions.
Never guarantee profit.
"""
)


researcher = make_agent(
    "Researcher",
    """
Perform web research with source-backed findings.

Never invent facts or URLs.

Every material claim should have evidence.

Mark unknown information as UNVERIFIED.
""",
    [web]
)


developer = make_agent(
    "Developer",
    """
Act as a software developer.

Produce maintainable code,
tests,
documentation,
and explicit assumptions.

Never claim code was executed unless it actually was.
"""
)


designer = make_agent(
    "Designer",
    """
Act as a visual and UI designer.

Produce:
- design specifications
- layouts
- asset prompts
- implementation guidance

Do not claim an asset exists unless it was actually generated.
"""
)


writer = make_agent(
    "Writer",
    """
Act as a professional content writer.

Follow:
- brief
- audience
- tone
- acceptance criteria

Return polished deliverables.
Flag missing information.
"""
)


reviewer1 = make_agent(
    "Reviewer 1",
    """
Perform strict quality control.

Check the work against:
- task
- requirements
- acceptance criteria
- factual evidence

Return PASS or FAIL.

If FAIL, list concrete defects.

Never invent fixes.
"""
)


reviewer2 = make_agent(
    "Reviewer 2",
    """
Perform independent final QA.

Look for:
- factual errors
- omissions
- formatting defects
- unsupported claims
- failure to meet requirements

Return PASS or FAIL.
"""
)


finance = make_agent(
    "Finance",
    """
Evaluate project economics.

Track:
- revenue
- external costs
- AI/tool costs
- review cost
- risk

Show arithmetic transparently.

Never present estimates as facts.
"""
)


# =========================
# MODELS
# =========================

class ChatIn(BaseModel):
    message: str
    project_id: Optional[str] = None


class ResearchIn(BaseModel):
    task: str
    max_retries: int = Field(
        default=MAX_RETRIES,
        ge=0,
        le=5
    )


class ApprovalIn(BaseModel):
    project_id: str
    action: str


# =========================
# RUN AGENT
# =========================

async def run_agent(agent, prompt):
    result = await Runner.run(
        agent,
        prompt
    )

    return result.final_output


# =========================
# BASIC ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
def home():

    index_file = Path(__file__).parent / "index.html"

    if not index_file.exists():
        return HTMLResponse(
            "<h1>AI Company is running</h1>"
        )

    return HTMLResponse(
        index_file.read_text(
            encoding="utf-8"
        )
    )


@app.get("/api/health")
def health():

    return {
        "ok": True,
        "service": "AI Company",
        "database": DB_PATH,
        "model_configured": bool(
            os.getenv("OPENAI_API_KEY")
        )
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

    project_id = (
        body.project_id
        or new_project(body.message)
    )

    log(
        project_id,
        "Manager",
        "message",
        body.message
    )

    output = await run_agent(
        manager,
        body.message
    )

    log(
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
# RESEARCH PIPELINE
# =========================

@app.post("/api/research")
async def research(body: ResearchIn):

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured."
        )

    project_id = new_project(
        body.task
    )

    plan = await run_agent(
        manager,
        "Create a research plan with acceptance criteria:\n"
        + body.task
    )

    log(
        project_id,
        "Manager",
        "plan",
        plan
    )

    prompt = (
        body.task
        + "\n\nPLAN:\n"
        + plan
    )

    research_output = ""
    review1 = ""
    review2 = ""

    for attempt in range(
        body.max_retries + 1
    ):

        log(
            project_id,
            "Researcher",
            "start",
            f"Attempt {attempt + 1}"
        )

        research_output = await run_agent(
            researcher,
            prompt
        )

        log(
            project_id,
            "Researcher",
            "result",
            research_output
        )

        review1 = await run_agent(
            reviewer1,
            "TASK:\n"
            + body.task
            + "\nRESEARCH:\n"
            + research_output
        )

        log(
            project_id,
            "Reviewer 1",
            "review",
            review1
        )

        if "PASS" not in review1.upper():

            if attempt < body.max_retries:

                prompt = (
                    body.task
                    + "\n\nREWORK REQUIRED:\n"
                    + review1
                )

                continue

            break

        review2 = await run_agent(
            reviewer2,
            "TASK:\n"
            + body.task
            + "\nRESEARCH:\n"
            + research_output
        )

        log(
            project_id,
            "Reviewer 2",
            "review",
            review2
        )

        if "PASS" in review2.upper():
            break

        if attempt < body.max_retries:

            prompt = (
                body.task
                + "\n\nSECOND QA REWORK REQUIRED:\n"
                + review2
            )

    final = await run_agent(
        manager,
        "Prepare the final deliverable.\n"
        "TASK:\n"
        + body.task
        + "\nRESEARCH:\n"
        + research_output
        + "\nQA1:\n"
        + review1
        + "\nQA2:\n"
        + review2
        + "\nSeparate verified from unverified information "
        "and include sources."
    )

    connection = db()

    connection.execute(
        "UPDATE projects SET status=? WHERE id=?",
        ("completed", project_id)
    )

    connection.commit()
    connection.close()

    log(
        project_id,
        "Manager",
        "final",
        final
    )

    return {
        "project_id": project_id,
        "final": final,
        "research": research_output,
        "review1": review1,
        "review2": review2
    }


# =========================
# JOB HUNTER
# =========================

@app.post("/api/jobs/search")
async def jobs_search(body: ResearchIn):

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured."
        )

    output = await run_agent(
        job_hunter,
        body.task
    )

    return {
        "results": output,
        "requires_human_approval": True
    }


# =========================
# OPPORTUNITY ANALYSIS
# =========================

@app.post("/api/jobs/analyze")
async def jobs_analyze(body: ChatIn):

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured."
        )

    output = await run_agent(
        analyst,
        body.message
    )

    return {
        "analysis": output
    }


# =========================
# APPROVALS
# =========================

@app.post("/api/approvals")
def approval(body: ApprovalIn):

    approval_id = str(
        uuid.uuid4()
    )

    connection = db()

    connection.execute(
        "INSERT INTO approvals VALUES(?,?,?,?,?)",
        (
            approval_id,
            body.project_id,
            body.action,
            "pending",
            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )

    connection.commit()
    connection.close()

    return {
        "approval_id": approval_id,
        "status": "pending",
        "message": (
            "Human approval required "
            "before external action."
        )
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
            """
            SELECT *
            FROM projects
            ORDER BY created_at DESC
            """
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
