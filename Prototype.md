### Prototype

---
#### Prototype Core Components:
- Frontend: A Streamlit web application provides the simple chatbot UI. It's user-friendly and abstracts away the complexity of the backend.
- Backend API: A FastAPI service acts as the central hub. It receives user requests, interacts with the knowledge base, and triggers the asynchronous patching jobs.
- Asynchronous Tasks: Celery workers process long-running tasks like patching and rebooting.
- Task Queue: Redis is used as a fast, in-memory message broker for the Celery tasks.
- State & Results: A PostgreSQL database stores job results, logs, and a structured record of all executed tasks for auditing.
- Persistent Knowledge Base: A separate schema in the PostgreSQL database will hold the predefined errors and solutions. A dedicated web UI (e.g., a simple form) will allow you to add or update this data.
- Automation Engine: Ansible Automation Platform (AAP) or AWX executes the pre-checks, patching, and post-checks on the Linux servers.
---
#### High-Level Workflow:
- A user submits a request via the Streamlit UI. The UI sends this request to the FastAPI backend.
- The FastAPI backend receives the request and, after basic validation, sends an asynchronous job to the Celery task queue (Redis).
- A Celery worker pulls the task from the queue and initiates an Ansible job via the AAP/AWX API.
- The worker periodically polls the AAP/AWX API for real-time status updates and stores the progress in the PostgreSQL database.
- Upon job completion, the worker retrieves the full Ansible log.
- The worker's internal parser scans the log for any failures. If a failure is found, the parser queries the PostgreSQL knowledge base for a matching error.
- The knowledge base returns a predefined solution, which the worker appends to the failure log.
- The final result, including success/failure logs and troubleshooting information, is saved to the PostgreSQL database.
- The Streamlit UI polls the FastAPI API, which in turn queries the PostgreSQL database for the final status and presents a clear, concise summary to the user.
- A separate, basic UI allows you to directly interact with the PostgreSQL knowledge base to add or modify error-solution pairs.
---
#### Project Structure
- Organize your files into a clean directory structure.
```
.
├── src/
│   ├── main.py
│   ├── app.py
│   ├── kb_app.py           # New: UI for the Knowledge Base
│   ├── requirements.txt
│   └── ...                 # Other Python files
├── Dockerfile.backend
├── Dockerfile.frontend
├── Dockerfile.kb           # New: for the knowledge base UI
├── openshift/
│   ├── 01_secrets.yaml     # AAP token and DB credentials
│   ├── 02_redis.yaml       # Redis deployment & service
│   ├── 03_postgres.yaml    # PostgreSQL deployment & persistent volume claim
│   ├── 04_db_migrations.yaml # Job to initialize the DB schema
│   ├── 05_app_backend.yaml   # FastAPI deployment & service
│   ├── 06_worker.yaml      # Celery worker deployment
│   ├── 07_app_frontend.yaml  # Streamlit deployment & service
│   ├── 08_kb_frontend.yaml   # New: Knowledge Base UI deployment & service
│   └── 09_routes.yaml      # Exposes services to the internet
```
---
### Step-by-Step Deployment
- Project Setup:
  - Create a new project in OpenShift.
  - Create a Secret for your AAP token and database credentials.
- Database and Persistent Storage:
  - Deploy PostgreSQL using a StatefulSet to ensure a stable network identity.
  - Define a Persistent Volume Claim (PVC) for PostgreSQL's data directory. This ensures that your knowledge base data persists even if the pod restarts.
  - Deploy Redis with a Deployment and a Service.
- Knowledge Base Initialization: Create a one-off Job that runs a script to create the known_issues table in the PostgreSQL database and populate it with a few predefined errors and solutions.
- Application Deployment:
  - Build and push container images for all three components: the FastAPI backend, the Streamlit frontend, and the knowledge base UI.
  - Deploy the FastAPI backend and Celery worker using separate Deployments but the same container image. This is a common pattern for OpenShift.
  - Deploy the Streamlit frontend using its own Deployment.
  - Deploy the new Knowledge Base UI using its own Deployment.
  - Use Services to expose each application component within the cluster.
- Exposing Services:
  - Create Routes for the FastAPI backend and the Streamlit frontend to make them accessible from outside the cluster.
  - Create a separate Route for the Knowledge Base UI so you can access it to add new errors and solutions. This is how you make it.
