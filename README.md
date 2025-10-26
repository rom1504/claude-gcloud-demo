# FastAPI + Cloud SQL + Cloud Tasks Demo

A full-stack application demonstrating Google Cloud Platform services: Cloud Run, Cloud SQL (PostgreSQL), and Cloud Tasks for background job processing.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌───────────────┐
│   Frontend  │─────▶│  Cloud Run   │─────▶│  Cloud SQL    │
│  (HTML/JS)  │      │  (FastAPI)   │      │ (PostgreSQL)  │
└─────────────┘      └──────┬───────┘      └───────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ Cloud Tasks  │
                     │   (Queue)    │
                     └──────────────┘
```

## Project Structure

```
.
├── main.py              # FastAPI backend application
├── static/
│   └── index.html       # Frontend HTML page
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container configuration
├── deploy.sh            # Deployment script
├── .env.example         # Environment variables template
├── .env                 # Local environment variables (gitignored)
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Features

### Backend (FastAPI)
- **Health Check** - `/api/health`
- **Items Management** - CRUD operations for items stored in PostgreSQL
  - `GET /api/items` - List all items
  - `POST /api/items` - Create new item
  - `DELETE /api/items/{id}` - Delete item
- **Background Tasks** - Prime number calculation using Cloud Tasks
  - `POST /api/tasks/prime` - Submit background task
  - `GET /api/tasks` - List all tasks
  - `GET /api/tasks/{id}` - Get task status
  - `POST /api/tasks/process-prime` - Worker endpoint (internal)

### Frontend
- Beautiful responsive UI with gradient design
- Real-time task status monitoring with auto-refresh
- Item management with add/delete functionality
- Background task submission for prime number calculation

### Infrastructure
- **Cloud Run**: Serverless container deployment
- **Cloud SQL**: Managed PostgreSQL database
- **Cloud Tasks**: Distributed task queue for background jobs

## Local Development

### Prerequisites
- Python 3.11+
- pip

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/rom1504/your-repo-name.git
cd your-repo-name
```

2. **Copy environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run locally** (uses SQLite by default)
```bash
python main.py
```

5. **Open browser** at `http://localhost:8080`

## Deployment to Google Cloud

### Prerequisites

1. [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
2. A Google Cloud project with billing enabled
3. Authenticate: `gcloud auth login`

### Step 1: Enable Required APIs

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com \
  cloudtasks.googleapis.com
```

### Step 2: Create Cloud SQL Instance

```bash
# Create PostgreSQL instance
gcloud sql instances create YOUR-DB-INSTANCE \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1

# Create database
gcloud sql databases create items_db --instance=YOUR-DB-INSTANCE

# Set root password
gcloud sql users set-password postgres \
  --instance=YOUR-DB-INSTANCE \
  --password=YOUR-PASSWORD
```

### Step 3: Create Cloud Tasks Queue

```bash
gcloud tasks queues create prime-calculator --location=us-central1
```

### Step 4: Deploy to Cloud Run

```bash
# Set environment variables
export PROJECT_ID="your-project-id"
export DB_INSTANCE="your-db-instance"
export DB_PASSWORD="your-db-password"
export SERVICE_URL="https://your-service-url.run.app"

# Deploy
gcloud run deploy fastapi-demo \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --add-cloudsql-instances ${PROJECT_ID}:us-central1:${DB_INSTANCE} \
  --set-env-vars \
    DATABASE_URL="postgresql://postgres:${DB_PASSWORD}@/items_db?host=/cloudsql/${PROJECT_ID}:us-central1:${DB_INSTANCE}",\
    GOOGLE_CLOUD_PROJECT=${PROJECT_ID},\
    SERVICE_URL=${SERVICE_URL} \
  --project ${PROJECT_ID}
```

### Step 5: Grant IAM Permissions

```bash
# Get the default compute service account
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")

# Grant necessary permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --role=roles/cloudsql.client

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --role=roles/cloudtasks.enqueuer
```

## Environment Variables

Required environment variables (set in `.env` for local, Cloud Run for production):

| Variable | Description | Example |
|----------|-------------|---------|
| `GOOGLE_CLOUD_PROJECT` | Your GCP project ID | `my-project-123` |
| `SERVICE_URL` | Your Cloud Run service URL | `https://service-xxx.run.app` |
| `DATABASE_URL` | PostgreSQL connection string | See `.env.example` |
| `CLOUD_TASKS_LOCATION` | Cloud Tasks region | `us-central1` |
| `CLOUD_TASKS_QUEUE` | Queue name | `prime-calculator` |

## API Documentation

Once deployed, visit:
- Frontend: `https://your-service-url.run.app`
- API Docs: `https://your-service-url.run.app/docs`
- OpenAPI: `https://your-service-url.run.app/openapi.json`

## Technologies Used

- **Backend**: FastAPI, Uvicorn, SQLAlchemy
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Database**: PostgreSQL (Cloud SQL)
- **Task Queue**: Google Cloud Tasks
- **Infrastructure**: Docker, Google Cloud Run
- **Language**: Python 3.11

## How Background Tasks Work

1. User submits a task via the frontend (e.g., "find 1000 prime numbers")
2. Backend creates a task record in the database (status: `pending`)
3. Task is enqueued to Cloud Tasks
4. Cloud Tasks invokes the worker endpoint asynchronously
5. Worker calculates prime numbers and updates the database (status: `completed`)
6. Frontend polls for updates and displays results

This architecture allows CPU-intensive operations to run without blocking the API response.

## Cost Considerations

### Google Cloud Free Tier (as of 2025)
- **Cloud Run**: 2M requests/month, 360K GB-seconds memory, 180K vCPU-seconds
- **Cloud SQL**: db-f1-micro instance eligible for free credits
- **Cloud Tasks**: 1M operations/month free

This demo should fit comfortably within free tier limits for development/testing.

## Security Notes

- **Never commit `.env` file** - Contains sensitive credentials
- **Use Secret Manager** for production - Store credentials securely
- **Rotate passwords** regularly
- **Restrict IAM permissions** to minimum required
- **Enable Cloud SQL SSL** for production deployments

## Troubleshooting

### Database Connection Issues
```bash
# Check Cloud SQL instance status
gcloud sql instances describe YOUR-INSTANCE

# Test connection from Cloud Run
gcloud run services update fastapi-demo --clear-cloudsql-instances
```

### Task Queue Not Processing
```bash
# Check queue status
gcloud tasks queues describe prime-calculator --location=us-central1

# View task queue
gcloud tasks list --queue=prime-calculator --location=us-central1
```

### View Logs
```bash
# Cloud Run logs
gcloud run services logs read fastapi-demo --limit=50

# Cloud SQL logs
gcloud sql operations list --instance=YOUR-INSTANCE
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

## License

MIT License - Feel free to use this project for learning and development.

## Author

Built with Claude Code
