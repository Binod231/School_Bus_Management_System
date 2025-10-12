# School Bus Management System

This is a comprehensive school bus management system built with FastAPI. It provides a robust platform for managing school bus routes, tracking buses in real-time, and facilitating communication between school administration, drivers, and guardians.

---

## Features

### Superadmin
- Manage schools and school admins.
- View system-wide statistics.

### Admin
- Manage drivers, students, and guardians for their school.
- Create and manage bus routes and bus stops.
- Assign drivers to buses.
- Monitor live bus locations.
- View and manage incident reports.
- View dashboard with key statistics.

### Driver
- View assigned trips and student lists.
- Start, update, and end trips.
- Update student boarding status (manually or via QR code).
- Report incidents.
- Send live location updates.

### Guardian
- View their children's profiles and trip histories.
- Track the live location of their child's bus.
- Receive notifications for boarding, arrivals, and incidents.
- Confirm their child's arrival.

---

## Technologies Used

- **Backend:** Python, FastAPI
- **Database:** PostgreSQL with SQLAlchemy for ORM
- **Asynchronous Programming:** `asyncio`
- **Authentication:** JWT (JSON Web Tokens) with OAuth2
- **Real-time Communication:** WebSockets
- **Caching:** Redis
- **Database Migrations:** Alembic
- **Push Notifications:** Firebase Cloud Messaging (FCM)
- **Containerization:** Docker, Docker Compose

---

## Project Structure

school_bus_management/
├── app/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── routes/
│   ├── schemas/
│   ├── services/
│   ├── utils/
│   ├── main.py
├── migrations/
├── tests/
├── .env
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt


---

## Setup and Installation

### Prerequisites

- Python 3.9+
- Docker and Docker Compose
- PostgreSQL client

### 1. Clone the repository

```bash
git clone <repository-url>
cd school_bus_management
2. Create a virtual environment
Bash

python3 -m venv venv
source venv/bin/activate
3. Install dependencies
Bash

pip install -r requirements.txt
4. Set up the database
Make sure you have a PostgreSQL server running. You can use the provided docker-compose.yml file for this.

5. Environment Variables
Copy the .env.example file to .env and update the values as needed.

Bash

cp .env.example .env
Key variables to update:

DATABASE_URL: The connection string for your PostgreSQL database.

SECRET_KEY: A secret key for JWT token generation.

SMTP_...: Your SMTP server details for sending emails.

FCM_CREDENTIALS_PATH: Path to your Firebase Admin SDK credentials file.

How to Run
Using Docker Compose (Recommended)
This is the easiest way to get the entire stack (FastAPI app, PostgreSQL, Redis) up and running.

Bash

docker-compose up --build
The application will be available at http://localhost:8000.

Using Uvicorn (for development)
If you prefer to run the FastAPI app directly on your host machine:

Start the database and Redis:

Bash

docker-compose up -d school_bus_db redis
Run the database migrations:

Bash

alembic upgrade head
Start the FastAPI server:

Bash

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
API Documentation
Once the application is running, you can access the interactive API documentation at http://localhost:8000/docs.

This will provide a complete list of all available API endpoints, their parameters, and response models.
