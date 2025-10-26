from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
import json
import os

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./items.db")

# SQLAlchemy setup
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database models
class ItemDB(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class TaskDB(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String, index=True)
    n_value = Column(Integer)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic models
class ItemCreate(BaseModel):
    name: str
    description: str

class ItemResponse(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True

class TaskCreate(BaseModel):
    n_value: int

class TaskResponse(BaseModel):
    id: int
    task_name: str
    n_value: int
    status: str
    result: str | None
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True

# FastAPI app
app = FastAPI(title="Simple FastAPI Backend with Database")

# Cloud Tasks configuration
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-project-id")
LOCATION = os.environ.get("CLOUD_TASKS_LOCATION", "us-central1")
QUEUE_NAME = os.environ.get("CLOUD_TASKS_QUEUE", "prime-calculator")
SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:8080")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to find N prime numbers
def find_n_primes(n: int) -> list[int]:
    """Find the first N prime numbers"""
    primes = []
    candidate = 2

    while len(primes) < n:
        is_prime = True
        for prime in primes:
            if prime * prime > candidate:
                break
            if candidate % prime == 0:
                is_prime = False
                break

        if is_prime:
            primes.append(candidate)

        candidate += 1

    return primes

# API endpoints
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Backend is running!", "database": "connected"}

@app.get("/api/hello/{name}")
async def hello(name: str):
    return {"message": f"Hello, {name}!", "status": "success"}

@app.get("/api/items", response_model=list[ItemResponse])
async def get_items():
    db = SessionLocal()
    try:
        items = db.query(ItemDB).order_by(ItemDB.created_at.desc()).all()
        return items
    finally:
        db.close()

@app.post("/api/items", response_model=ItemResponse)
async def create_item(item: ItemCreate):
    db = SessionLocal()
    try:
        db_item = ItemDB(name=item.name, description=item.description)
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
    finally:
        db.close()

@app.delete("/api/items/{item_id}")
async def delete_item(item_id: int):
    db = SessionLocal()
    try:
        item = db.query(ItemDB).filter(ItemDB.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        db.delete(item)
        db.commit()
        return {"message": "Item deleted successfully"}
    finally:
        db.close()

# Legacy endpoint for backward compatibility
@app.get("/api/data")
async def get_data():
    db = SessionLocal()
    try:
        items = db.query(ItemDB).all()
        return {
            "items": [
                {"id": item.id, "name": item.name, "description": item.description}
                for item in items
            ]
        }
    finally:
        db.close()

# Task endpoints
@app.post("/api/tasks/prime", response_model=TaskResponse)
async def create_prime_task(task: TaskCreate):
    """Create a new background task to calculate prime numbers"""
    db = SessionLocal()
    try:
        # Create task record in database
        db_task = TaskDB(
            task_name=f"Find first {task.n_value} primes",
            n_value=task.n_value,
            status="pending"
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)

        # Create Cloud Task
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(PROJECT_ID, LOCATION, QUEUE_NAME)

        task_payload = {
            "task_id": db_task.id,
            "n_value": task.n_value
        }

        http_request = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{SERVICE_URL}/api/tasks/process-prime",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(task_payload).encode()
        }

        cloud_task = {"http_request": http_request}

        # Submit task to Cloud Tasks
        response = client.create_task(request={"parent": parent, "task": cloud_task})

        return db_task
    finally:
        db.close()

@app.post("/api/tasks/process-prime")
async def process_prime_task(request: Request):
    """Background worker endpoint that processes prime number calculations"""
    try:
        body = await request.json()
        task_id = body["task_id"]
        n_value = body["n_value"]

        db = SessionLocal()
        try:
            # Update task status to processing
            task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.status = "processing"
            db.commit()

            # Calculate prime numbers
            primes = find_n_primes(n_value)

            # Update task with results
            task.status = "completed"
            task.result = json.dumps(primes)
            task.completed_at = datetime.utcnow()
            db.commit()

            return {"status": "success", "task_id": task_id}
        finally:
            db.close()

    except Exception as e:
        # Mark task as failed
        db = SessionLocal()
        try:
            task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
            if task:
                task.status = "failed"
                task.result = str(e)
                task.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks", response_model=list[TaskResponse])
async def get_tasks():
    """Get all tasks"""
    db = SessionLocal()
    try:
        tasks = db.query(TaskDB).order_by(TaskDB.created_at.desc()).all()
        return tasks
    finally:
        db.close()

@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """Get a specific task by ID"""
    db = SessionLocal()
    try:
        task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task
    finally:
        db.close()

# Serve static files (frontend)
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
