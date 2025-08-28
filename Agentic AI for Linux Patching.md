# Agentic AI for Linux Patching

### Brief Summary of the Idea
The proposed idea is an AI-powered chatbot (Agentic AI) designed to automate pre-checks, patching, reboot, and post-checks on Linux servers during maintenance activities. The chatbot will take user requests, validate them, execute automated Ansible playbooks for pre/post-validation, patching, and reboot, and provide real-time feedback to users.
The system will leverage: Ansible Automation Platform/AWX/Ansible Playbook for execution,
Celery for asynchronous job handling, A Knowledge Base (KB) integrated with AI to suggest solutions, troubleshoot errors, and provide recommendations during or after patching, An easy-to-use web interface deployed on OpenShift/Kubernetes for scalability.

