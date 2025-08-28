# AI Agent for Automated Linux Patching
---
###  Overview
- This document outlines a proposal to develop an AI-powered chatbot designed to automate and streamline Linux OS patching operations. The agent will leverage our existing infrastructure and integrate with the Red Hat Ansible Automation Platform (AAP) to provide intelligent, automated support. This proof-of-concept (PoC) will be deployed on OpenShift, utilizing a microservices architecture for scalability and flexibility.
---
### Key Functionality
- The AI agent will simplify the patching workflow by handling key tasks and providing a user-friendly interface.

Core Operations: 
- Pre-Patching Validation: The agent will execute a pre-check playbook to ensure target hosts are ready for patching.
- Patching and Reboot: The agent will trigger the apply and reboot playbook to install patches and manage host reboots.
- Post-Patching Verification: A post-patching playbook will be run to verify the kernel level and confirm the desired state has been achieved.

Agent Features:
- Task Management: Users can interact with the chatbot to select and execute the desired patching task by specifying a wave number (1 to 4).
- Status and Reporting: The agent will monitor job status in real-time. Upon completion, it will generate two distinct output files:
- Success Log: A file containing the hostname and "OK" for all successful hosts.
- Failure Log: A file capturing the full error message for any failed playbook run.
- Intelligent Troubleshooting: For hosts with patching failures, the agent will automatically parse the error output, query a centralized knowledge base for known issues, and append a corresponding solution to the failure log. This provides immediate context and support.
- Simplified User Interface: The primary goal is to abstract the complexity of raw Ansible output. The chatbot will present users with a clear, concise, and actionable summary directly within the chat interface.

---
### Architecture
```
flowchart LR
  UI[Streamlit Chat UI] --> API[FastAPI Control API]
  API -->|calls| AAP[AAP REST API]
  API --> Worker[Python Worker (Celery/RQ)]
  Worker --> Parser[Parser & KB Lookup]
  Parser --> KB[KB Service (Flask/FastAPI)]
  Parser --> Storage[(MinIO or PVC)]
  UI -->|downloads| Storage
```
---
### Key Component
- Streamlit UI: Chat-like interface, user picks:
  - Pre-check
  - Apply+Reboot
  - Post-check
  - Check Status
  - Download Results
- FastAPI Control API: Orchestrates job launch, status check, and file retrieval.
- Worker: Processes job results, queries KB, writes success/failure reports.
- KB Service: Simple Flask/FastAPI app to store KB entries and return solutions.
- Storage: PVC or MinIO (for reports).
- OpenShift Deployment: All containers Python-based.
- Technical Architecture
---

This PoC will be built with a microservices architecture and deployed on OpenShift. A simple, easily updatable web server will host the centralized knowledge base.
