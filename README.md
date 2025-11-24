#  Distributed Task Queue & Job Processor

## ✨ Features

### Core Functionality
-  **REST API** for job submission and status tracking
-  User authentication with username/password and session cookies
-  API key support for external integrations
-  **Atomic job leasing** using PostgreSQL `SELECT FOR UPDATE SKIP LOCKED`
-  **Automatic retry logic** with exponential backoff
-  **Dead Letter Queue (DLQ)** for failed jobs
-  **Idempotency keys** to prevent duplicate job submissions
-  **Multi-tenancy** with per-user isolation
-  **Rate limiting** (per-minute and per-hour quotas)
-  **Concurrent job limits** per tenant

### Reliability & Observability
-  **Heartbeat mechanism** for long-running jobs
-  **Graceful worker shutdown** (finishes current job)
-  **Race condition protection** with optimistic locking
-  **Comprehensive logging** (structured JSON logs with trace IDs)
-  **Metrics endpoint** (jobs, tenants, workers, system health)
-  **Job history audit trail**
-  **Health check endpoint**

### User Interface
-  **Registration & Login page** with secure authentication
-  **Real-time dashboard** with WebSocket support
-  **Job submission** via web UI
-  **Live statistics** and job monitoring
-  **DLQ viewer** and manual retry capability
-  **Django Admin panel** for advanced management


### Component Roles

- **PostgreSQL**: Persistent storage for jobs, users, tenants, and audit logs
- **Redis**: Message broker for WebSocket real-time updates
- **Django Web**: REST API and session-based authentication
- **Django Channels**: WebSocket server for real-time dashboard
- **Workers**: Job processors that poll and execute tasks

---

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+ (for WebSocket support)
- Docker & Docker Compose (recommended)

---

## 🚀 Quick Start (Docker)

### 1. Clone and setup
```bash
git clone <repository-url>
cd taskqueue
```

### 2. Start all services
```bash
docker compose up -d
```

This will automatically:
-  Start PostgreSQL database
-  Start Redis cache
-  Run database migrations
-  **Create admin superuser** (username: `admin`, password: `admin`)
-  Start web server (port 8000)
-  Start WebSocket server (port 8001)
-  Start 3 worker processes

### 3. Access the system

**User Dashboard:**
- URL: http://localhost:8000/
- Register a new account or use existing credentials

**Admin Panel:**
- URL: http://localhost:8000/admin/
- Username: `admin`
- Password: `admin`

### 4. Register & Login

1. Go to http://localhost:8000/
2. Click **Register** tab
3. Fill in:
   - Username: `yourname`
   - Email: `you@company.com`
   - Password: `yourpassword`
4. Click **Create Account**
5. You'll be automatically logged in and redirected to the dashboard

### 5. Submit your first job

In the dashboard:
1. Select **Job Type**: `Test Job`
2. Enter **Payload**:
   ```json
   {
     "duration": 5,
     "should_fail": false
   }
   ```
3. Set **Priority**: `0`
4. Click **Submit Job**
5. Watch the job progress in real-time!


## 📊 Dashboard Features

The dashboard provides:

### Live Statistics
- **Pending**: Jobs waiting to be processed
- **Running**: Jobs currently being executed
- **Completed**: Successfully finished jobs
- **Failed / DLQ**: Jobs that failed after all retries

### Job Submission Form
- Choose from 5 pre-built job types
- Custom JSON payload
- Priority setting (higher = processed first)
- Real-time submission feedback

### Recent Jobs Table
- Job ID, Type, Status, Priority
- Retry count
- Creation timestamp
- Auto-refreshes every 5 seconds

### Dead Letter Queue
- Failed jobs after max retries
- Error messages
- Retry capability


## 📈 Observability

### Logging

All major events are logged with **job IDs as trace identifiers**:

**View logs:**
```bash
# All logs
docker compose logs -f

# Worker logs only
docker compose logs -f worker1 worker2 worker3

# Web server logs
docker compose logs -f web

# Filter by job ID
docker compose logs -f | grep "job_id"
```

and also check the folder named logs with file name  = taskqueue.log

**Example log output:**
```
taskqueue_web    | [INFO] 2025-11-23 12:11:08 jobs.services - Job created: b045a462-6e64-4c91-b133-4410716f2fbf (type: test_job)
taskqueue_worker3| [INFO] 2025-11-23 12:11:08 jobs.models - Job leased: b045a462-6e64-4c91-b133-4410716f2fbf by worker worker-3
taskqueue_worker3| [INFO] 2025-11-23 12:11:08 workers.worker - Processing job b045a462-6e64-4c91-b133-4410716f2fbf
taskqueue_worker3| [DEBUG] 2025-11-23 12:11:08 workers.worker - Heartbeat started for job b045a462-6e64-4c91-b133-4410716f2fbf
taskqueue_worker3| [INFO] 2025-11-23 12:11:08 workers.processor - Executing test_job handler for job b045a462-6e64-4c91-b133-4410716f2fbf
taskqueue_worker3| [INFO] 2025-11-23 12:11:13 jobs.models - Job completed: b045a462-6e64-4c91-b133-4410716f2fbf
taskqueue_worker3| [INFO] 2025-11-23 12:11:13 workers.worker - Job b045a462-6e64-4c91-b133-4410716f2fbf completed successfully
```

## 📡 API Endpoints

### Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobs/` | Submit a new job |
| GET | `/api/jobs/` | List all jobs (paginated) |
| GET | `/api/jobs/{id}/` | Get job details |
| GET | `/api/jobs/stats/` | Get job statistics |
| GET | `/api/jobs/{id}/history/` | Get job history |
| POST | `/api/jobs/{id}/cancel/` | Cancel a pending job |

### Dead Letter Queue
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dlq/` | List DLQ items |
| GET | `/api/dlq/{id}/` | Get DLQ item details |
| POST | `/api/dlq/{id}/retry/` | Retry a failed job from DLQ |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       👤 USER (WEB BROWSER)                         │
│                                                                     │
│  Landing Page (/)         →         Dashboard (/dashboard/)        │
│  • Registration                      • Submit jobs                  │
│  • Login                             • Monitor status               │
│  • Session cookie created            • View DLQ                     │
└──────────┬──────────────────────────────┬───────────────────────────┘
           │                              │
           │ HTTP (Session Cookies)       │ WebSocket (Real-time)
           │                              │
┌──────────▼──────────────────────────────▼───────────────────────────┐
│                     DJANGO APPLICATION                              │
│                         (Port 8000)                                  │
│                                                                     │
│  ┌────────────────────┐              ┌─────────────────────┐       │
│  │   WEB SERVER       │              │  CHANNELS (ASGI)    │       │
│  │   (Daphne ASGI)    │              │  WebSocket Server   │       │
│  │                    │              │                     │       │
│  │  Django URLs:      │              │  JobConsumer        │       │
│  │  • /                │              │  ws://...           │       │
│  │  • /dashboard/      │              │                     │       │
│  │  • /api/tenants/    │              │  Real-time job      │       │
│  │  • /api/jobs/       │              │  updates pushed     │       │
│  │  • /api/dlq/        │              │  to browser         │       │
│  └─────────┬──────────┘              └──────────┬──────────┘       │
│            │                                    │                   │
│  ┌─────────▼────────────────────────────────────▼──────────┐       │
│  │           MIDDLEWARE LAYER                               │       │
│  │  • SessionMiddleware (checks session cookie)             │       │
│  │  • CSRFMiddleware (validates CSRF token)                 │       │
│  │  • TenantMiddleware (sets request.tenant)                │       │
│  └─────────┬────────────────────────────────────────────────┘       │
│            │                                                         │
│  ┌─────────▼─────────────────────────────────────────────────┐     │
│  │              REST API LAYER                               │     │
│  │                                                           │     │
│  │  TenantViewSet:                 JobViewSet:              │     │
│  │  • POST /register/             • POST /jobs/             │     │
│  │  • POST /login/                • GET /jobs/              │     │
│  │  • POST /logout/               • GET /jobs/{id}/         │     │
│  │  • GET /me/                    • GET /jobs/stats/        │     │
│  │                                • POST /jobs/{id}/cancel/ │     │
│  │  DLQViewSet:                                             │     │
│  │  • GET /dlq/                                             │     │
│  │  • POST /dlq/{id}/retry/                                 │     │
│  │                                                           │     │
│  │  Permissions:                                            │     │
│  │  • HasTenantAccess (checks request.tenant)               │     │
│  └─────────┬─────────────────────────────────────────────────┘     │
│            │                                                         │
│  ┌─────────▼─────────────────────────────────────────────────┐     │
│  │            BUSINESS LOGIC LAYER                           │     │
│  │                                                           │     │
│  │  JobService:                    TenantService:           │     │
│  │  • create_job()                • check_rate_limit()      │     │
│  │  • retry_dlq_job()             • check_concurrent_quota()│     │
│  │  • get_stats()                 • track_job_submission()  │     │
│  │                                                           │     │
│  │  Checks:                                                  │     │
│  │  ✓ Idempotency (duplicate prevention)                    │     │
│  │  ✓ Rate limits (10 jobs/min, 100/hour per tenant)       │     │
│  │  ✓ Concurrent quota (5 running jobs max)                 │     │
│  └─────────┬─────────────────────────────────────────────────┘     │
└────────────┼───────────────────────────────────────────────────────┘
             │
             │
┌────────────▼─────────────────────────┐    ┌─────────────────────┐
│      POSTGRESQL DATABASE             │    │   REDIS CACHE       │
│          (Port 5432)                 │    │   (Port 6379)       │
│                                      │    │                     │
│  Tables:                             │    │  Purpose:           │
│  ┌────────────────────────┐          │    │  • Channel Layer    │
│  │ auth_user              │          │    │  • WebSocket groups │
│  │ • username             │          │    │  • Pub/sub messages │
│  │ • password (hashed)    │          │    │                     │
│  │ • email                │          │    │  Groups:            │
│  └────────────────────────┘          │    │  tenant_{id}_jobs   │
│                                      │    │                     │
│  ┌────────────────────────┐          │    └─────────────────────┘
│  │ tenants                │          │
│  │ • user_id (FK)         │          │
│  │ • max_concurrent_jobs  │          │
│  │ • max_jobs_per_minute  │          │
│  │ • max_jobs_per_hour    │          │
│  └────────────────────────┘          │
│                                      │
│  ┌────────────────────────┐          │
│  │ jobs (QUEUE)           │◄─────────┼─── Worker polls here
│  │ • status (pending/     │          │
│  │   running/completed)   │          │
│  │ • job_type             │          │
│  │ • payload              │          │
│  │ • priority             │          │
│  │ • tenant_id (FK)       │          │
│  │ • worker_id            │          │
│  │ • lease_until          │          │
│  │ • version (lock)       │          │
│  │ • retry_count          │          │
│  └────────────────────────┘          │
│                                      │
│  ┌────────────────────────┐          │
│  │ dead_letter_queue      │          │
│  │ • original_job_id      │          │
│  │ • error_message        │          │
│  │ • retried (bool)       │          │
│  └────────────────────────┘          │
│                                      │
│  ┌────────────────────────┐          │
│  │ job_history            │          │
│  │ • job_id (FK)          │          │
│  │ • event_type           │          │
│  │ • message              │          │
│  │ • timestamp            │          │
│  └────────────────────────┘          │
│                                      │
│  ┌────────────────────────┐          │
│  │ idempotency_keys       │          │
│  │ • key                  │          │
│  │ • job_id (FK)          │          │
│  │ • expires_at           │          │
│  └────────────────────────┘          │
│                                      │
│  ┌────────────────────────┐          │
│  │ rate_limit_tracker     │          │
│  │ • tenant_id (FK)       │          │
│  │ • window_start         │          │
│  │ • job_count            │          │
│  └────────────────────────┘          │
└────────────┬─────────────────────────┘
             │
             │ SELECT FOR UPDATE SKIP LOCKED
             │ (atomic job leasing)
             │
┌────────────▼─────────────────────────────────────────────────┐
│                    WORKER POOL                               │
│                                                              │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐         │
│  │ Worker 1 │      │ Worker 2 │      │ Worker 3 │         │
│  │          │      │          │      │          │         │
│  │ Loop:    │      │ Loop:    │      │ Loop:    │         │
│  │ 1. Poll  │      │ 1. Poll  │      │ 1. Poll  │         │
│  │ 2. Lease │      │ 2. Lease │      │ 2. Lease │         │
│  │ 3. Run   │      │ 3. Run   │      │ 3. Run   │         │
│  │ 4. Ack/  │      │ 4. Ack/  │      │ 4. Ack/  │         │
│  │    Nack  │      │    Nack  │      │    Nack  │         │
│  │          │      │          │      │          │         │
│  │ Heartbeat│      │ Heartbeat│      │ Heartbeat│         │
│  │ (30s)    │      │ (30s)    │      │ (30s)    │         │
│  └──────────┘      └──────────┘      └──────────┘         │
│                                                              │
│  JobProcessor handles:                                      │
│  • test_job, send_email, process_data                       │
│  • generate_report, call_webhook                            │
└──────────┬───────────────────────────────────────────────────┘
           │
           │ On job completion
           │ sends update via channels
           │
┌──────────▼─────────────────────┐
│  Channel Layer (Redis)         │
│  tenant_{id}_jobs group        │
│  Broadcasts to all WebSocket   │
│  connections in that group     │
└──────────┬─────────────────────┘
           │
           │ WebSocket message
           │
┌──────────▼─────────────────────┐
│  Browser receives update       │
│  Dashboard auto-refreshes:     │
│  • Job status                  │
│  • Stats counters              │
│  • DLQ list                    │
└────────────────────────────────┘
```

## 💼 Job Types

The system supports 5 job types out of the box:

### 1. Test Job
```json
{
  "job_type": "test_job",
  "payload": {
    "duration": 5,
    "should_fail": false,
    "failure_rate": 0.0
  }
}
```

### 2. Send Email
```json
{
  "job_type": "send_email",
  "payload": {
    "to": "user@example.com",
    "subject": "Hello",
    "body": "Email content",
    "duration": 2,
    "should_fail": false
  }
}
```

### 3. Process Data
```json
{
  "job_type": "process_data",
  "payload": {
    "data": [1, 2, 3],
    "operation": "transform",
    "duration": 3,
    "should_fail": false
  }
}
```

### 4. Generate Report
```json
{
  "job_type": "generate_report",
  "payload": {
    "report_type": "monthly",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "duration": 5,
    "should_fail": false
  }
}
```

### 5. Call Webhook
```json
{
  "job_type": "call_webhook",
  "payload": {
    "url": "https://example.com/webhook",
    "method": "POST",
    "data": {},
    "duration": 1,
    "should_fail": false
  }
}
```

**Note:** All job types support `duration` (execution time in seconds) and `should_fail` (test failures) parameters.

---

## 🎯 Rate Limiting

Each tenant has configurable limits:

### Default Quotas
- **Concurrent Jobs**: 5 (max running at once)
- **Per Minute**: 10 jobs
- **Per Hour**: 100 jobs

### Testing Rate Limits

**Test Concurrent Limit:**
Submit 6 long-running jobs quickly:
```javascript
// In browser console on dashboard
for (let i = 0; i < 6; i++) {
  fetch('/api/jobs/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    credentials: 'same-origin',
    body: JSON.stringify({
      job_type: 'test_job',
      payload: {duration: 30, should_fail: false},
      priority: 0
    })
  }).then(r => r.json()).then(d => console.log(d));
}
```

**Expected:** First 5 succeed, 6th returns:
```json
{
  "error": "Concurrent job limit (5) reached"
}
```

**Expected:** First 10 succeed, 11th returns HTTP 429.

### Modify Limits

Via Django Admin (http://localhost:8000/admin/):
1. Go to **Tenants**
2. Click your tenant
3. Edit `max_concurrent_jobs`, `max_jobs_per_minute`, `max_jobs_per_hour`
4. Save

---


### Metrics

**Get statistics:**
```bash
http://localhost:8000/api/jobs/stats/
```

**Response:**
```json
{
  "total": 150,
  "pending": 5,
  "running": 3,
  "completed": 140,
  "failed": 1,
  "dead_letter": 1,
  "success_rate": 93.33,
  "avg_duration_seconds": 4.5
}
```

### Job History

Track every state change:
```bash
http://localhost:8000/api/jobs/{JOB_ID}/history/
```

**Response:**
```json
[
  {
    "id": 1,
    "job_id": "b045a462-6e64-4c91-b133-4410716f2fbf",
    "event_type": "created",
    "status": "pending",
    "worker_id": null,
    "error_message": null,
    "timestamp": "2025-11-23T12:11:08.500Z",
    "metadata": {
      "retry_count": 0,
      "job_type": "test_job",
      "tenant_id": "abc-123..."
    }
  },
  {
    "id": 2,
    "job_id": "b045a462-6e64-4c91-b133-4410716f2fbf",
    "event_type": "completed",
    "status": "completed",
    "worker_id": "worker-3",
    "error_message": null,
    "timestamp": "2025-11-23T12:11:13.621Z",
    "metadata": {
      "retry_count": 0,
      "job_type": "test_job",
      "tenant_id": "abc-123..."
    }
  }
]
```

---

## 🧪 Testing

### Run All Tests
```bash
# Using Docker
docker compose exec web python manage.py test --verbosity=2

# Or use the test script
./run_tests.sh
```

### Test Coverage

Tests cover:
-  Job creation and submission
-  Idempotency key handling
-  Rate limiting (concurrent, per-minute, per-hour)
-  Job leasing and worker processing
-  Retry logic and exponential backoff
-  DLQ operations
-  Race condition handling
-  Heartbeat mechanism
-  API authentication
-  Dashboard integration

**Example test output:**
```
test_create_job (jobs.tests.JobTestCase) ... ok
test_idempotency_key (jobs.tests.JobTestCase) ... ok
test_rate_limit_per_minute (tenants.tests.RateLimitingTestCase) ... ok
test_concurrent_quota (tenants.tests.RateLimitingTestCase) ... ok
test_job_retry_logic (workers.tests.WorkerTestCase) ... ok
test_dlq_creation (jobs.tests.DLQTestCase) ... ok

----------------------------------------------------------------------
Ran 28 tests in 12.345s

OK
```

---

## 🛠️ Development

### Local Setup (without Docker)

1. **Install dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Setup PostgreSQL:**
```bash
createdb taskqueue_db
```

3. **Setup Redis:**
```bash
redis-server
```

4. **Configure environment:**
```bash
cp env_template.txt .env
# Edit .env with your database credentials
```

5. **Run migrations:**
```bash
python manage.py migrate
```

6. **Create superuser:**
```bash
python manage.py createsuperuser
```

7. **Run services:**
```bash
# Terminal 1: Web server
python manage.py runserver

# Terminal 2: Channels (WebSocket)
daphne -b 0.0.0.0 -p 8001 taskqueue.asgi:application

# Terminal 3-5: Workers
python manage.py run_worker --worker-id worker-1
python manage.py run_worker --worker-id worker-2
python manage.py run_worker --worker-id worker-3
```

## 🐳 Docker Commands

### Service Management
```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart web
docker compose restart worker1

# View logs
docker compose logs -f web
docker compose logs -f worker1 worker2 worker3

# Check service status
docker compose ps
```

### Database Operations
```bash
# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Access Django shell
docker compose exec web python manage.py shell

# Access PostgreSQL shell
docker compose exec db psql -U postgres -d taskqueue_db
```


## 📚 Project Structure

```
taskqueue/
├── taskqueue/              # Django project settings
│   ├── settings.py         # Main configuration
│   ├── urls.py            # Root URL routing
│   ├── asgi.py            # ASGI config for WebSockets
│   └── wsgi.py            # WSGI config
├── jobs/                   # Core job models and API
│   ├── models.py          # Job, DLQ, History models
│   ├── views.py           # REST API views
│   ├── serializers.py     # DRF serializers
│   ├── services.py        # Business logic
│   ├── consumers.py       # WebSocket consumers
│   ├── admin.py           # Django admin config
│   └── tests.py           # Job tests
├── tenants/                # Multi-tenancy and auth
│   ├── models.py          # Tenant model
│   ├── views.py           # Auth endpoints
│   ├── middleware.py      # Auth middleware
│   └── tests.py           # Tenant tests
├── workers/                # Job processors
│   ├── worker.py          # Main worker logic
│   ├── processor.py       # Job type handlers
│   ├── tests.py           # Worker tests
│   └── management/
│       └── commands/
│           └── run_worker.py  # Worker command
├── dashboard/              # Frontend UI
│   └── templates/
│       └── dashboard/
│           ├── landing.html   # Login/Register
│           └── index.html     # Main dashboard
├── docker-compose.yml      # Docker orchestration
├── Dockerfile             # Container definition
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

---


### Rate Limiting

Default tenant quotas (editable in Django Admin):
- `max_concurrent_jobs`: 5
- `max_jobs_per_minute`: 10
- `max_jobs_per_hour`: 100

---

## Optional / Conceptual Add-Ons (Stretch) 

## Auto-Scaling Workers (Conceptual)

While the current implementation uses a fixed number of workers (3), here's how auto-scaling could be implemented in production:

### **Approach 1: Kubernetes Horizontal Pod Autoscaler (HPA)**

**How it works:**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: taskqueue-workers
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: taskqueue-worker
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: pending_jobs_count
      target:
        type: AverageValue
        averageValue: "10"
```

**Scaling Logic:**
- **Scale UP** when: Pending jobs > 10 per worker OR CPU > 70%
- **Scale DOWN** when: Pending jobs < 3 per worker AND CPU < 30%
- **Cool-down period**: 5 minutes between scale events

**Benefits:**
-  Automatic response to load spikes
-  Cost-efficient (scale down during low traffic)
-  Native Kubernetes integration

---

### **Approach 2: Custom Metrics-Based Scaling**

**Monitoring Script:**
```python
# autoscaler.py
def should_scale(metrics):
    pending_jobs = metrics['pending']
    running_jobs = metrics['running']
    active_workers = metrics['workers']
    
    # Scale up if queue is growing
    if pending_jobs > active_workers * 10:
        return 'up', min(active_workers * 2, 20)
    
    # Scale down if workers are idle
    if pending_jobs < active_workers * 2 and active_workers > 3:
        return 'down', max(active_workers // 2, 3)
    
    return 'none', active_workers
```

**Implementation:**
1. Query `/api/jobs/stats/` endpoint every 30 seconds
2. Calculate: `pending_jobs / active_workers`
3. If ratio > 10: Add workers
4. If ratio < 2: Remove workers (wait for current jobs to finish)
5. Use Docker Compose or ECS to start/stop containers

---

### **Approach 3: Queue-Depth Based (AWS ECS)**

**AWS CloudWatch Alarm:**
```json
{
  "MetricName": "PendingJobsCount",
  "Namespace": "TaskQueue",
  "Threshold": 50,
  "ComparisonOperator": "GreaterThanThreshold",
  "Period": 60,
  "EvaluationPeriods": 2,
  "Statistic": "Average",
  "AlarmActions": ["arn:aws:autoscaling:policy/scale-up"]
}
```

**Scaling Policy:**
- Monitor `SELECT COUNT(*) FROM jobs WHERE status='pending'`
- Publish to CloudWatch every minute
- Scale ECS tasks based on queue depth

---

### **Current System Preparation**

The system is **already designed** for horizontal scaling:

 **Stateless Workers**: Workers don't share state  
 **Atomic Job Leasing**: `SELECT FOR UPDATE SKIP LOCKED` prevents race conditions  
 **Database-Backed Queue**: Shared queue accessible by all workers  
 **Graceful Shutdown**: Workers finish current job before terminating  
 **Unique Worker IDs**: Each worker has a unique identifier  

**To enable scaling, you would:**
1. Remove `container_name` from `docker-compose.yml`
2. Use environment variable for worker ID: `--worker-id $HOSTNAME`
3. Deploy as Kubernetes Deployment or ECS Service
4. Configure HPA/Auto Scaling Group

---

## 🎯 Design Trade-offs & Decisions

### **1. Database-Backed Queue vs. Message Broker (Redis/RabbitMQ)**

** Chosen: PostgreSQL as Queue**

**Why:**
-  **Simplicity**: Single source of truth, no sync issues
-  **ACID Guarantees**: Strong consistency and durability
-  **Complex Queries**: Easy filtering, stats, history
-  **Built-in Locking**: `SELECT FOR UPDATE SKIP LOCKED`
-  **No Additional Infra**: Already have PostgreSQL

**Trade-off:**
-  Slightly slower than in-memory queues (acceptable for most workloads)
-  Database load increases with job volume (mitigated with indexes)

**Note:** Redis is ALREADY used for WebSocket channel layer (Django Channels), 
but the JOB QUEUE itself uses PostgreSQL.

**When to switch the JOB QUEUE to Redis:**
- If throughput > 10,000 jobs/second
- If job payloads are very small and ephemeral
- If you don't need complex queries or job history
- If you need pub/sub patterns for job distribution

### **2. Session Cookies vs. JWT Tokens**

** Chosen: Django Session Cookies**

**Why:**
-  **Simplicity**: Django's built-in auth, no extra config
-  **Server-Side Control**: Can revoke sessions instantly
-  **Smaller Request Size**: No large JWT in every request
-  **Automatic CSRF Protection**: Django middleware handles it

**Trade-off:**
-  Requires sticky sessions in multi-server setups (use Redis session backend)
-  Not ideal for mobile apps or third-party API access

**When to use JWT:**
- If need true stateless authentication
- If deploying across multiple data centers

---

### **3. Polling vs. Push Notifications**

** Chosen: Worker Polling**

**Why:**
-  **Simple**: No complex event system
-  **Reliable**: Workers self-recover, no lost messages
-  **Scalable**: Add workers without coordination
-  **Self-Balancing**: Workers naturally distribute load

**Trade-off:**
-  2-second delay before job processing (acceptable)
-  Slight database load from polling (minimal with proper indexes)

**When to use Push:**
- If need sub-second latency
- If have millions of workers (polling overhead)

---

### **4. Optimistic Locking (Version Field) vs. Pessimistic Locking**

** Chosen: Hybrid Approach**

**Implementation:**
- **Pessimistic** for job leasing (`SELECT FOR UPDATE SKIP LOCKED`)
- **Optimistic** for job updates (`version` field)

**Why:**
-  **Race Condition Protection**: Multiple workers can't grab same job
-  **Update Safety**: Prevents overwriting concurrent changes
-  **Performance**: Lock only held during SELECT, not entire processing

**Trade-off:**
-  Slightly more complex than pure pessimistic locking
-  Much better performance than holding locks during job execution

---

### **5. Heartbeat Mechanism vs. No Heartbeat**

** Chosen: Heartbeat with Lease Extension**

**Why:**
-  **Long Job Support**: Jobs can run longer than lease duration
-  **Crash Detection**: If worker dies, lease expires and job is retried
-  **Resource Protection**: Prevents zombie jobs

**Trade-off:**
-  Additional database writes during job execution
-  Extra thread per worker for heartbeat

**When to skip:**
- If all jobs finish in < 10 seconds (use short lease)
- If job re-execution is idempotent and cheap

---

### **6. Three Fixed Workers vs. Dynamic Scaling**

** Chosen: Fixed Workers (for simplicity)**

**Why:**
-  **Predictable**: Easy to reason about
-  **Simple Config**: No orchestration complexity
-  **Good for Demo**: Shows multi-worker behavior
-  **Easy to Scale**: Just add more worker services

**Trade-off:**
-  Waste resources during low traffic
-  Can't auto-respond to load spikes


