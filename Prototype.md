### Prototype

---
#### Prototype Core Components:
- Web Interface (Frontend): A simple chat UI built with Streamlit to handle user input and display real-time updates.
- Chatbot API (Backend): A FastAPI server that receives user requests, validates them, and sends them to Celery.
- Task Queue: A Redis instance to hold the asynchronous jobs.
- Asynchronous Workers: A Celery worker that listens to the Redis queue.
- Automation Engine: The Ansible Automation Platform (AAP) or AWX will be called by the Celery worker to execute the playbooks.
- Database: PostgreSQL to store the state and results of the jobs.
---
#### High-Level Workflow:
- A user types a command like "Patch server web-01 with Group-1" into the Streamlit UI.
- The Streamlit app sends this request to the FastAPI backend.
- The FastAPI endpoint validates the request and then calls a Celery task.
- The Celery task is put into a queue in Redis.
- A Celery worker picks up the task from Redis.
- The worker triggers an Ansible job in AAP/AWX with the server and patch details.
- The Celery worker periodically checks the status of the Ansible job and stores the progress in the PostgreSQL database.
- The FastAPI backend polls the PostgreSQL database to get the real-time status of the job.
- The Streamlit UI displays the updates to the user as they happen, like "Pre-checks started," "Patching in progress," and "Patching completed."
---
#### Project Structure
- Organize your files into a clean directory structure.
```
.
├── src/
│ ├── main.py        # FastAPI backend & Celery task
│ ├── app.py         # Streamlit frontend
│ └── requirements.txt  # Python dependencies
├── Dockerfile.backend    # For the FastAPI service and Celery workers
├── Dockerfile.frontend   # For the Streamlit UI
├── openshift/
│ ├── deployment-api.yaml      # Defines the FastAPI deployment
│ ├── deployment-worker.yaml   # Defines the Celery worker deployment
│ ├── service-api.yaml         # Exposes the FastAPI service internally
│ ├── route-api.yaml           # Exposes the FastAPI service to the public
│ ├── redis.yaml               # Redis deployment
│ ├── postgres.yaml            # PostgreSQL deployment
```
- Dockerfiles: Two separate Dockerfiles since the backend and frontend have different entry points. (for FastAPI and Celery)
- OpenShift YAML Files
- The redis.yaml & postgres.yaml yml files tell OpenShift how to run each component
- The deployment-api.yaml creates a single pod for the FastAPI API.
- The deployment-worker.yaml creates a separate pod for the Celery worker.
- The service-api.yaml exposes the FastAPI API to other pods within the cluster.
- The route-api.yaml creates a public-facing URL for your Streamlit application to access the FastAPI API.
---
### Step-by-Step Deployment
- Create a New OpenShift Projec
- Create a Secret for Ansible Token
- Build and Push Docker Images: Build your images and push them to OpenShift's internal registry
- Deploy Database Components (redis & 
