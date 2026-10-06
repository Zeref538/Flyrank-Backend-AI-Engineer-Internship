import os

from dotenv import load_dotenv

# Read .env before anything looks at the environment. It never overrides a
# variable that is already set, so inside docker compose the values compose
# passes in win over the file.
load_dotenv()

from fastapi import Body, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from llm.client import LLMError
from llm.schema import TriageIn
from llm.triage import classify

# The only line in the API layer that knows storage exists. Set DATABASE_URL and
# the same routes run on Postgres; leave it unset and they run on SQLite.
if os.environ.get("DATABASE_URL"):
    import db_postgres as db
else:
    import db

app = FastAPI(
    title="Task API",
    version="1.0",
    description="A to-do list you can create, read, update and delete over HTTP. "
    "Storage is PostgreSQL when DATABASE_URL is set, otherwise a SQLite file. "
    "Either way the tasks survive a restart.",
)

db.init()  # create the tasks table on startup if it isn't there, and seed it once


@app.exception_handler(HTTPException)
def json_error(request, exc):
    """Every error leaves as {"error": "..."} instead of FastAPI's {"detail": ...}."""
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
def bad_body(request, exc):
    """A client mistake is a 400, in the same shape as every other error.

    Name the field. "Body must be a JSON object" tells the caller nothing when
    the real problem is that `text` was 2,001 characters long.
    """
    problems = []
    for err in exc.errors():
        # loc looks like ("body", "text"); drop the "body" part.
        field = ".".join(str(p) for p in err["loc"][1:])
        problems.append(f"{field}: {err['msg']}" if field else err["msg"])
    return JSONResponse(
        {"error": "; ".join(problems) or "Body must be a JSON object"}, status_code=400)


def clean_title(body: dict) -> str:
    """A title must be present, be text, and not be blank. Anything else is a 400."""
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(400, "Field 'title' is required and must not be empty")
    return title.strip()


def find(task_id: int):
    task = db.one_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return task


@app.get("/", summary="What this API is and where to go next")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.post("/triage", summary="Classify a support message into a team and urgency")
def triage(body: TriageIn):
    """Input is validated before a single token is spent."""
    try:
        result, _ = classify(body.text)
    except LLMError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return result


@app.get("/health", summary="Say whether the server and its database can answer")
def health():
    """A load balancer calls this every few seconds and stops sending users to
    a server that fails it. "ok" without asking the database would keep traffic
    flowing to a server whose every real request is about to fail."""
    try:
        db.ping()
    except Exception as exc:  # any driver error means the same thing here: no database
        return JSONResponse({"status": "degraded", "db": "down",
                             "error": type(exc).__name__}, status_code=503)
    return {"status": "ok", "db": "ok"}


@app.get("/tasks", summary="List every task")
def list_tasks():
    return db.all_tasks()


@app.get("/tasks/{task_id}", summary="Get one task by id, or 404")
def get_task(task_id: int):
    return find(task_id)


@app.post("/tasks", status_code=201, summary="Create a task from a title")
def create_task(body: dict = Body(...)):
    # SQLite hands out the id now (INTEGER PRIMARY KEY AUTOINCREMENT), so the
    # old max(id)+1 trick is gone -- and so is the chance of two requests racing
    # for the same number.
    return db.insert(clean_title(body))

@app.put("/tasks/{task_id}", summary="Change a task's title, its done flag, or both")
def update_task(task_id: int, body: dict = Body(...)):
    find(task_id)  # 404s before we touch the database
    if "title" not in body and "done" not in body:
        raise HTTPException(400, "Send at least one of 'title' or 'done'")
    title = clean_title(body) if "title" in body else None
    done = None
    if "done" in body:
        if not isinstance(body["done"], bool):
            raise HTTPException(400, "Field 'done' must be true or false")
        done = body["done"]
    return db.update(task_id, title=title, done=done)


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task, returning no body")
def delete_task(task_id: int):
    find(task_id)
    db.delete(task_id)
