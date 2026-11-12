# 🚌 EDURIDE — Real-Time School Bus Fleet Management Backend

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/ORM-SQLAlchemy%202.0%20(asyncpg)-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2015-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Broker-Redis%207%20%2F%20Valkey-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Container-Docker%20Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![AWS Ready](https://img.shields.io/badge/Deployment-AWS%20(EC2%20%2B%20RDS)-FF9900.svg?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)

**EDURIDE** is a high-concurrency, asynchronous fleet management and child-safety telemetry platform built with **FastAPI**, **SQLAlchemy 2.0 (asyncpg)**, **PostgreSQL 15**, and **Redis/Valkey**.

It provides high-frequency GPS ingestion (every 3–5 seconds), in-memory spherical geofencing (< 120-meter arrival detection), live parent tracking via secure WebSockets (`wss://`), automated push notifications (FCM), and complete role-based fleet administrative workflows.

---

##  Table of Contents
- [Why EDURIDE?](#-why-eduride)
- [System Architecture](#-system-architecture)
- [Key Technical Features](#-key-technical-features)
- [Role-Based Access & Capabilities](#-role-based-access--capabilities)
- [Project Directory Structure](#-project-directory-structure)
- [Quickstart: Local Development](#-quickstart-local-development)
- [Production Deployment on AWS](#-production-deployment-on-aws)
- [API Reference & Telemetry Ingestion](#-api-reference--telemetry-ingestion)
- [Environment Configuration](#-environment-configuration)
- [Testing & Verification](#-testing--verification)
- [License](#-license)

---

##  Why EDURIDE?

Unlike general-purpose e-commerce delivery logistics, school transit operations have zero margin for error:
1. **Child Safety & Parent Visibility:** Unnotified 8-minute delays leave children on roadside corners in adverse weather and flood school administration lines with panicked calls. EDURIDE delivers live bus coordinates to parents with sub-second propagation delay.
2. **Hands-Free Driver Automation:** Drivers cannot safely look down at mobile screens to tap "Arrived" while operating a bus with children onboard. EDURIDE automates stop arrival detection using mathematical geofencing.
3. **Lean Startup Cost Governance:** Runs on an optimized **Single-AZ AWS stack (EC2 Graviton + Amazon RDS) for ~$26.70/month** (Free Tier eligible), with a clean migration path to multi-node ECS Fargate when scaled.

---

## System Architecture

```
                                  EDURIDE BACKEND TOPOLOGY
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                 Amazon VPC (10.0.0.0/16)                               │
 │                                                                                        │
 │  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
 │  │                         Amazon EC2 Host (t4g.small)                              │  │
 │  │                                                                                  │  │
 │  │   HTTPS / WSS (Port 443) ──> [ Nginx TLS Reverse Proxy ]                         │  │
 │  │                                        │                                         │  │
 │  │    ┌───────────────────────────────────┼──────────────────────────────────────┐  │  │
 │  │    │                     Internal Docker Bridge Network                       │  │  │
 │  │    │                                   ▼                                      │  │  │
 │  │    │              [ school_bus_web_prod (FastAPI + Uvicorn) ]                 │  │  │
 │  │    │              • Non-root runtime user (appuser, UID 1000)                 │  │  │
 │  │    │              • Ingestion: POST /api/v1/driver/trips/{id}/location        │  │  │
 │  │    │              • In-Memory Geofencing (Haversine < 120m)                   │  │  │
 │  │    │              • WebSocket Manager: Single-use ticket auth over wss://     │  │  │
 │  │    │                                   │                                      │  │  │
 │  │    │             Pub/Sub Broadcast     │  Single-Use Tickets                  │  │  │
 │  │    │             ┌─────────────────────┴──────────────────────┐               │  │  │
 │  │    │             ▼                                            ▼               │  │  │
 │  │    │  [ school_bus_redis_prod (Redis 7 Alpine) ]                              │  │  │
 │  │    │  • Ephemeral pub/sub channel: trip:{trip_id}:telemetry                   │  │  │
 │  │    │  • 60-second atomic ticket store (getdel)                                │  │  │
 │  │    │  • No public host ports (internal container network only)                │  │  │
 │  │    └───────────────────────────────────┬──────────────────────────────────────┘  │  │
 │  └────────────────────────────────────────┼─────────────────────────────────────────┘  │
 │                                           │                                            │
 │                                           │ postgresql+asyncpg://                      │
 │                                           │ Port 5432 (SSL Enforced)                   │
 │                                           ▼                                            │
 │  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
 │  │                     Amazon RDS PostgreSQL 15 (Single-AZ)                         │  │
 │  │  • Private Subnet: Ingress restricted strictly to EC2 Security Group             │  │
 │  │  • Tables: users, schools, buses, bus_routes, bus_stops, trips, location_updates  │  │
 │  │  • Composite Index: idx_location_updates_trip_timestamp (trip_id, created_at DESC)│  │
 │  │  • Connection Pool: pool_pre_ping=True, pool_recycle=1800                        │  │
 │  └──────────────────────────────────────────────────────────────────────────────────┘  │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Technical Features

* **Sub-Millisecond Geofencing Engine:** Calculates great-circle distance using Python’s spherical Haversine formula (~0.02ms execution), eliminating 25,000 spatial calculations/minute from the database engine.
* **Async PostgreSQL Persistence (`asyncpg`):** Fully asynchronous database I/O using SQLAlchemy 2.0 with connection pre-pinging (`pool_pre_ping=True`) and socket recycling (`pool_recycle=1800`) to prevent AWS VPC firewall idle disconnects.
* **Distributed Pub/Sub Fan-Out (Redis / Valkey):** Telemetry ingestion publishes to Redis channels (`trip:{id}:telemetry`), decoupling high-frequency driver writes from long-lived guardian WebSocket streams across worker processes.
* **Hardened WebSocket Security (`wss://`):** Replaces URL-based JWT query parameters with single-use, 60-second tickets issued via authenticated HTTPS (`POST /api/v1/auth/ws-ticket`) and redeemed atomically in Redis (`getdel`).
* **Zero-Trust Network Operations:** Zero open SSH ports on EC2—host administration is performed strictly via **AWS Systems Manager (SSM) Session Manager**.
* **Eager Relationship Tree Loading:** Avoids SQLAlchemy `MissingGreenlet` exceptions through explicit `selectinload` joining on routes, stops, and student manifests.

---

## Role-Based Access & Capabilities

| Role | Core Capabilities |
|---|---|
| **Superadmin** | Onboard multi-tenant schools, manage school administrators, view system-wide platform health, analytics, and safety compliance metrics. |
| **School Admin** | Manage drivers, students, and parent guardians; configure bus routes, stop sequences, and geofence coordinates; assign buses and drivers; view real-time operations dashboard. |
| **Driver** | View daily morning/afternoon trip rosters; start and finalize trips; stream live GPS telemetry; update student boarding/disembarking status manually or via **QR Code scans**; report road incidents. |
| **Guardian** | Track child's bus in real time on an interactive map; receive instant push notifications (FCM) when the bus enters the 120m stop geofence, when child boards, and when child disembarks; confirm arrival. |

---

##  Project Directory Structure

```bash
school_bus_management/
├── app/
│   ├── core/
│   │   ├── cache.py          # Redis / Valkey client & connection pool
│   │   ├── config.py         # Pydantic BaseSettings & environment loading
│   │   ├── jwt.py            # OAuth2 & JWT token generation / validation
│   │   └── security.py       # Password hashing & authorization dependencies
│   ├── db/
│   │   ├── base.py           # SQLAlchemy DeclarativeBase
│   │   └── session.py        # Async engine & AsyncSessionLocal factory
│   ├── models/               # SQLAlchemy 2.0 ORM models
│   │   ├── bus.py            # Bus, BusRoute, BusStop, BusRouteStop, BusDriver
│   │   ├── incident.py       # Incident reports & resolution tracking
│   │   ├── school.py         # School entity & administration
│   │   ├── student.py        # Student profile & guardian association
│   │   ├── trip.py           # Trip, TripStudent, LocationUpdate
│   │   └── user.py           # User entity & RBAC roles
│   ├── routes/               # FastAPI APIRouters
│   │   ├── admin.py          # School admin management & dispatch endpoints
│   │   ├── auth.py           # Login, token refresh, and WebSocket ticket issue
│   │   ├── bus.py            # Bus & route CRUD endpoints
│   │   ├── driver.py         # Driver trip operations & GPS location ingestion
│   │   ├── guardian.py       # Parent live tracking & student status
│   │   ├── incident.py       # Incident logging & resolution
│   │   ├── public.py         # Public landing page health & analytics
│   │   └── superadmin.py     # Multi-tenant school oversight
│   ├── schemas/              # Pydantic request / response schemas
│   ├── services/             # Business logic & database interaction
│   │   ├── analytics.py      # Aggregated metrics & dashboard reporting
│   │   ├── bus.py            # Route stop sequencing & stop lookups
│   │   ├── notification.py   # FCM push notification dispatcher
│   │   └── trip.py           # Trip creation, Haversine math, location persistence
│   ├── utils/
│   │   ├── fcm.py            # Firebase Admin SDK integration
│   │   └── websocket.py      # Room-based WebSocket connection manager
│   ├── migrations/           # Alembic database migration scripts
│   │   ├── versions/         # Revision histories
│   │   └── env.py            # Async Alembic runner (NullPool)
│   └── main.py               # FastAPI entrypoint, CORS, lifespan, and WebSocket endpoint
├── aws_user_data.sh          # EC2 Cloud-Init automated bootstrap script
├── docker-compose.local.yml  # Local developer stack (App + Postgres + Redis)
├── docker-compose.prod.yml   # Production EC2 stack (App + Redis + Nginx)
├── Dockerfile                # Multi-stage hardened build (non-root appuser)
├── nginx.conf                # Nginx reverse proxy with TLS & WebSocket upgrades
├── requirements.txt          # Python dependencies
└── verify_counts.py          # End-to-end data integrity validation script
```

---

##  Quickstart: Local Development

### 1. Prerequisites
* Python 3.11+
* Docker & Docker Compose
* Git

### 2. Clone & Configure
```bash
git clone https://github.com/Binod231/Schoo-_Bus_Management_System.git
cd Schoo-_Bus_Management_System

# Copy environment template
cp .env.example .env
```

### 3. Run with Docker Compose (Recommended)
This boots the application, local PostgreSQL 13, and Redis 7 on a unified bridge network:

```bash
docker-compose -f docker-compose.local.yml up --build
```

* **Interactive API Documentation (Swagger):** `http://localhost:8000/docs`
* **Alternative ReDoc UI:** `http://localhost:8000/redoc`
* **Health Check Endpoint:** `http://localhost:8000/health`

###  Running Manually (Without Docker)
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start local PostgreSQL and Redis containers
docker run -d --name local_postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d --name local_redis -p 6379:6379 redis:7-alpine

# Apply database migrations
alembic upgrade head

# Start FastAPI server with live reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

##  Production Deployment on AWS

### 1. Provisioning AWS Infrastructure
Follow the step-by-step commands to launch your Amazon RDS PostgreSQL database and Amazon EC2 host:

```bash
# 1. Create Web & RDS Security Groups
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)

EC2_SG=$(aws ec2 create-security-group \
    --group-name school-bus-ec2-sg \
    --description "Allow HTTP/HTTPS to EC2" \
    --vpc-id $VPC_ID --query "GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id $EC2_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $EC2_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

RDS_SG=$(aws ec2 create-security-group \
    --group-name school-bus-rds-sg \
    --description "Allow PostgreSQL from EC2 only" \
    --vpc-id $VPC_ID --query "GroupId" --output text)

aws ec2 authorize-security-group-ingress \
    --group-id $RDS_SG --protocol tcp --port 5432 --source-group $EC2_SG

# 2. Launch Amazon RDS PostgreSQL 15 Instance (Single-AZ Starter)
aws rds create-db-instance \
    --db-instance-identifier school-bus-db \
    --db-instance-class db.t4g.micro \
    --engine postgres \
    --engine-version 15.4 \
    --allocated-storage 20 \
    --storage-type gp3 \
    --master-username postgres \
    --master-user-password "YourSecureMasterPassword2026!" \
    --vpc-security-group-ids $RDS_SG \
    --backup-retention-period 7 \
    --no-publicly-accessible \
    --no-multi-az

# 3. Launch Amazon EC2 Host with Cloud-Init Bootstrap
aws ec2 run-instances \
    --image-id ami-0c101f26f147fa7fd \
    --instance-type t4g.small \
    --security-group-ids $EC2_SG \
    --iam-instance-profile Name=AmazonSSMManagedInstanceCore \
    --user-data file://aws_user_data.sh \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=school-bus-web}]'
```

### 2. Launching Services via AWS SSM
Connect to your EC2 instance via **AWS Systems Manager Session Manager** (no SSH key or port 22 needed):

```bash
aws ssm start-session --target <INSTANCE_ID>

# Clone repo and start stack
git clone https://github.com/Binod231/Schoo-_Bus_Management_System.git
cd Schoo-_Bus_Management_System
cp .env.example .env
# Edit .env with your RDS Endpoint and secrets
docker-compose -f docker-compose.prod.yml up -d --build
```

---

##  API Reference & Telemetry Ingestion

### Ingesting Driver GPS Telemetry
Drivers stream location pings every 3–5 seconds:

```bash
POST /api/v1/driver/trips/{trip_id}/location
Authorization: Bearer <DRIVER_JWT_TOKEN>
Content-Type: application/json

{
  "latitude": 27.71724,
  "longitude": 85.32396,
  "speed": 24.5,
  "heading": 180.0,
  "device_timestamp": "2026-11-12T08:30:00Z"
}
```

**Response (with automated 120m Geofence Arrival Alert):**
```json
{
  "latitude": 27.71724,
  "longitude": 85.32396,
  "speed": 24.5,
  "heading": 180.0,
  "device_timestamp": "2026-11-12T08:30:00Z",
  "arrived_stop": {
    "stop_id": 3,
    "stop_name": "North Gate Station",
    "distance_meters": 34.8
  }
}
```

### Subscribing to Live WebSockets (Guardians & Admin)
1. **Request Single-Use Ticket (HTTPS):**
   ```bash
   POST /api/v1/auth/ws-ticket?trip_id=1
   Authorization: Bearer <GUARDIAN_JWT_TOKEN>
   ```
   *Response:* `{"ticket": "8f3b2d1a-4c5e-49b2-9a01-2e7d8f9c1b3a", "expires_in": 60}`

2. **Connect over WSS:**
   ```bash
   wscat -c "wss://api.eduride.com/ws/trips/1/location?ticket=8f3b2d1a-4c5e-49b2-9a01-2e7d8f9c1b3a"
   ```
   *Streams live coordinate frames directly from Redis Pub/Sub.*

---

##  Environment Configuration

| Variable | Description | Example / Default |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string (`asyncpg`) | `postgresql+asyncpg://postgres:pass@db-host:5432/school_bus_db` |
| `SECRET_KEY` | 256-bit cryptographic secret for JWT signing | `your-super-secret-key-change-in-production` |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifespan in minutes | `10080` (7 days) |
| `REDIS_HOST` | Redis cache & message broker hostname | `redis` (Docker) or `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `FCM_CREDENTIALS_PATH` | Path to Google Firebase Service Account JSON | `/app/firebase-admin-key.json` |
| `BACKEND_CORS_ORIGINS` | Whitelisted CORS origins for web portals | `["http://localhost:3000", "https://eduride.com"]` |
| `SMTP_SERVER` | SMTP host for incident & welcome emails | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |

---

##  Testing & Verification

Run the end-to-end data integrity validation script to verify database connection pooling, active trip lookups, and student boarding counts:

```bash
python verify_counts.py
```

*Expected output:*
```text
Connecting to DB...
Fetching active trips for School 1...
--- Trip 80 ---
Status: IN_PROGRESS
Total Students: 14
Arrived Count: 2
VERIFICATION PASSED: The code correctly counts arrived students.
```

---

##  License

This project is licensed under the **MIT License** — feel free to use, modify, and distribute for your own fleet workloads.
