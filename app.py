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

app = FastAPI(title="AI Company", version="1.0.0")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS projects(
      id TEXT PRIMARY KEY, name TEXT, task TEXT, status TEXT,
      budget REAL DEFAULT 0, revenue REAL DEFAULT 0, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT,
      agent TEXT, event_type TEXT, message TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS approvals(
      id TEXT PRIMARY KEY, project_id TEXT, action TEXT,
      status TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS opportunities(
      id TEXT PRIMARY KEY, title TEXT, source TEXT, url TEXT,
      price REAL DEFAULT 0, estimated_cost REAL DEFAULT 0,
      estimated_profit REAL DEFAULT 0, risk TEXT, raw TEXT, created_at TEXT
    );
    """)
    c.commit(); c.close()

init_db()

def log(project_id, agent, event_type, message):
    c=db()
    c.execute("INSERT INTO events(project_id,agent,event_type,message,created_at) VALUES(?,?,?,?,?)",
              (project_id,agent,event_type,message,datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()

def new_project(task, budget=0, revenue=0):
    pid=str(uuid.uuid4())
    c=db()
    c.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?)",
              (pid, task[:80], task, "running", budget, revenue, datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
    return pid

def make_agent(name, instructions, tools=None):
    kwargs={"name":name, "instructions":instructions}
    if MODEL: kwargs["model"]=MODEL
    if tools: kwargs["tools"]=tools
    return Agent(**kwargs)

web = WebSearchTool(search_context_size="high", external_web_access=True)

manager = make_agent("Manager", """You are the CEO/Project Manager of an AI service company.
You own the final internal decision. Break tasks into explicit steps, assign specialists,
set acceptance criteria, watch budget, and never claim an external action was completed
unless the application actually performed it. Keep external submissions, contracts,
payments, account changes and irreversible actions behind human approval.""")
job_hunter = make_agent("Job Hunter", """Find current public freelance opportunities using live web research.
Do not fabricate jobs. Return title, source, URL, buyer requirements when public, apparent budget,
deadline if available, required skills, and evidence URL. Do not submit applications or contact
buyers. Respect marketplace terms and use official integrations where available.""", [web])
analyst = make_agent("Opportunity Analyst", """Analyze a freelance opportunity. Estimate effort,
AI/tool cost, human-review cost, platform fees if known, risk, and contribution margin.
State assumptions explicitly. Do not guarantee profit.""")
researcher = make_agent("Researcher", """Perform web research with source-backed findings.
Never invent facts or URLs. Every material claim needs evidence. Mark unknown fields UNVERIFIED.""", [web])
developer = make_agent("Developer", """Act as a software developer. Produce maintainable code,
tests, documentation and explicit assumptions. Never claim code was executed unless it was.""")
designer = make_agent("Designer", """Act as a visual/UI designer. Produce clear design specifications,
layout decisions, asset prompts and implementation-ready guidance. Do not claim an asset exists unless generated.""")
writer = make_agent("Writer", """Act as a professional content writer. Follow the brief, audience,
tone and acceptance criteria. Return polished deliverables and flag missing information.""")
reviewer1 = make_agent("Reviewer 1", """Perform strict quality control against the task and acceptance criteria.
Return PASS or FAIL plus concrete defects. Verify evidence where applicable. Never invent fixes.""")
reviewer2 = make_agent("Reviewer 2", """Perform independent final QA. Look for factual errors, omissions,
formatting defects, unsupported claims, and failure to meet client requirements. Return PASS or FAIL.""")
finance = make_agent("Finance", """Evaluate project economics. Track revenue, estimated external costs,
model/tool costs, review cost and risk. Give arithmetic transparently. Never present an estimate as a fact.""")

class ChatIn(BaseModel):
    message: str
    project_id: Optional[str] = None

class ResearchIn(BaseModel):
    task: str
    max_retries: int = Field(default=MAX_RETRIES, ge=0, le=5)

class ApprovalIn(BaseModel):
    project_id: str
    action: str

async def run_agent(agent, prompt):
    r = await Runner.run(agent, prompt)
    return r.final_output

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((Path(__file__).parent/"index.html").read_text(encoding="utf-8"))

@app.get("/api/health")
def health():
    return {"ok": True, "database": DB_PATH, "model_configured": bool(os.getenv("OPENAI_API_KEY"))}

@app.post("/api/chat")
async def chat(body: ChatIn):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "OPENAI_API_KEY is not configured.")
    pid=body.project_id or new_project(body.message)
    log(pid,"Manager","message",body.message)
    out=await run_agent(manager, body.message)
    log(pid,"Manager","response",out)
    return {"project_id":pid,"response":out}

@app.post("/api/research")
async def research(body: ResearchIn):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "OPENAI_API_KEY is not configured.")
    pid=new_project(body.task)
    plan=await run_agent(manager, "Create a research plan with acceptance criteria:\n"+body.task)
    log(pid,"Manager","plan",plan)
    prompt=body.task+"\n\nPLAN:\n"+plan
    research_out=""; review1=""; review2=""
    for attempt in range(body.max_retries+1):
        log(pid,"Researcher","start",f"Attempt {attempt+1}")
        research_out=await run_agent(researcher,prompt)
        log(pid,"Researcher","result",research_out)
        review1=await run_agent(reviewer1,"TASK:\n"+body.task+"\nRESEARCH:\n"+research_out)
        log(pid,"Reviewer 1","review",review1)
        if "PASS" not in review1.upper():
            if attempt < body.max_retries:
                prompt=body.task+"\n\nREWORK REQUIRED:\n"+review1
                continue
            break
        review2=await run_agent(reviewer2,"TASK:\n"+body.task+"\nRESEARCH:\n"+research_out)
        log(pid,"Reviewer 2","review",review2)
        if "PASS" in review2.upper():
            break
        if attempt < body.max_retries:
            prompt=body.task+"\n\nSECOND QA REWORK REQUIRED:\n"+review2
    final=await run_agent(manager,
        "Prepare the final deliverable.\nTASK:\n"+body.task+
        "\nRESEARCH:\n"+research_out+"\nQA1:\n"+review1+"\nQA2:\n"+review2+
        "\nSeparate verified from unverified information and include sources.")
    c=db(); c.execute("UPDATE projects SET status=? WHERE id=?",("completed",pid)); c.commit(); c.close()
    log(pid,"Manager","final",final)
    return {"project_id":pid,"final":final,"research":research_out,"review1":review1,"review2":review2}

@app.post("/api/jobs/search")
async def jobs_search(body: ResearchIn):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "OPENAI_API_KEY is not configured.")
    out=await run_agent(job_hunter, body.task)
    return {"results":out, "requires_human_approval":True}

@app.post("/api/jobs/analyze")
async def jobs_analyze(body: ChatIn):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "OPENAI_API_KEY is not configured.")
    out=await run_agent(analyst, body.message)
    return {"analysis":out}

@app.post("/api/approvals")
def approval(body: ApprovalIn):
    aid=str(uuid.uuid4())
    c=db()
    c.execute("INSERT INTO approvals VALUES(?,?,?,?,?)",
              (aid,body.project_id,body.action,"pending",datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
    return {"approval_id":aid,"status":"pending","message":"Human approval required before external action."}

@app.get("/api/projects")
def projects():
    c=db()
    rows=[dict(x) for x in c.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()]
    c.close(); return rows

@app.get("/api/events/{project_id}")
def events(project_id:str):
    c=db()
    rows=[dict(x) for x in c.execute("SELECT * FROM events WHERE project_id=? ORDER BY id",(project_id,)).fetchall()]
    c.close(); return rows
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agents import Agent, Runner, WebSearchTool

app = FastAPI(title="AI Company v3")

researcher = Agent(
    name="Researcher",
    model="gpt-5.6",
    instructions="""You are the Web Research employee.
Use live web search. Never invent facts or URLs.
Every important claim must have a source URL.
Return structured results and mark uncertain fields UNVERIFIED.""",
    tools=[WebSearchTool(search_context_size="high", external_web_access=True)],
)

reviewer = Agent(
    name="Reviewer",
    model="gpt-5.6",
    instructions="""You are strict QA.
Review the research against the user's task.
Return exactly:
STATUS: PASS or FAIL
DEFECTS:
- ...
If PASS, say why the evidence is sufficient.
If FAIL, specify exactly what the Researcher must re-check.
Never invent corrections.""",
)

manager = Agent(
    name="Manager",
    model="gpt-5.6",
    instructions="""You are the project manager.
Turn the user's request into a clear research plan, delegate to Researcher,
send results to Reviewer, and when needed create a precise rework instruction.
Only approve results after QA passes.""",
)

class Task(BaseModel):
    task: str
    max_retries: int = 2

@app.post("/run")
async def run(body: Task):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "OPENAI_API_KEY is missing.")

    events = []
    plan = await Runner.run(manager, "Create a concise research plan for:\n"+body.task)
    events.append({"agent":"Manager","type":"plan","output":plan.final_output})

    research_prompt = body.task + "\n\nMANAGER PLAN:\n" + plan.final_output
    final_research = ""
    final_review = ""

    for attempt in range(body.max_retries + 1):
        events.append({"agent":"Researcher","type":"start","attempt":attempt+1})
        rr = await Runner.run(researcher, research_prompt)
        final_research = rr.final_output
        events.append({"agent":"Researcher","type":"result","attempt":attempt+1,"output":final_research})

        vr = await Runner.run(
            reviewer,
            "USER TASK:\n"+body.task+
            "\n\nRESEARCH:\n"+final_research
        )
        final_review = vr.final_output
        events.append({"agent":"Reviewer","type":"review","attempt":attempt+1,"output":final_review})

        if "STATUS: PASS" in final_review.upper():
            break

        if attempt < body.max_retries:
            repair = await Runner.run(
                manager,
                "Create a precise rework instruction for the Researcher.\n"
                "Original task:\n"+body.task+
                "\nResearch:\n"+final_research+
                "\nReviewer defects:\n"+final_review
            )
            research_prompt = body.task + "\n\nREWORK INSTRUCTION:\n" + repair.final_output
            events.append({"agent":"Manager","type":"rework","attempt":attempt+1,"output":repair.final_output})

    final = await Runner.run(
        manager,
        "Produce the final deliverable for the user.\n"
        "Task:\n"+body.task+
        "\nResearch:\n"+final_research+
        "\nQA:\n"+final_review+
        "\nClearly distinguish verified and unverified information. Include source URLs."
    )
    events.append({"agent":"Manager","type":"final","output":final.final_output})

    return {"final": final.final_output, "research": final_research,
            "review": final_review, "events": events}

