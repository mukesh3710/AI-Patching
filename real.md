### Agentic AI
- Use-case for SNO + AAP. Below is a practical, end-to-end plan that gets you from “job runs in AAP” → “live status on a web UI,” while keeping AAP’s internal DB intact and streaming events to an external database in real time.
------
#### Architecture at a glance
- Platform: Single-Node OpenShift (SNO) with a StorageClass available and the internal OpenShift image registry enabled.
- Automation: AAP Controller (via Operator) + your custom Execution Environment (EE) image.
- Internal DB: AAP’s PostgreSQL (managed by the operator or external—unchanged).
- External DB MVP: MongoDB (great for real-time with Change Streams).
- Ingestion path (pick one):
A. External Logging from AAP → Fluent Bit/Logstash → DB (no app code).
B. Ansible callback plugin (HTTP/Logstash) in your EE → tiny “Ingest API” → DB (more control).
C. Poll AAP API for /jobs + /events (simplest, not true push).
- Web app: Backend service (REST + WebSocket/SSE) + lightweight UI, both on OpenShift.
- Optional scale-up: Kafka/AMQ Streams between AAP and DB for buffering at scale.

------
#### End-to-end workflow (data flow)
- Job runs in AAP using your custom EE.
- Internal persistence: AAP writes job + event records to its internal Postgres (unchanged behavior).
- Real-time stream to external DB:
- Either AAP’s External Logging forwards structured job events to a collector (Fluent Bit/Logstash), which writes to the external DB, or
- Your EE’s callback plugin posts events to an Ingest API service which writes to the DB.
- Web app subscribes to DB updates (e.g., MongoDB Change Streams) and shows live job status, host-level results, and event details.

---
Step-by-step plan
---
### Prereqs on SNO
- Default StorageClass and persistent storage.
- OpenShift Internal Registry enabled (for your EE image).
- Ingress/Route available (for AAP UI, web app UI, and ingestion endpoints).
- Access: oc/kubectl, cluster-admin, and AAP subscription entitlements.
---
### Install AAP on OpenShift
- In OperatorHub, install the Ansible Automation Platform Operator.
- Create the AAP Controller instance (namespace like aap), ensuring:
- Controller’s PostgreSQL is provisioned (operator-managed or external).
- A route to the AAP UI is created and reachable.
- Validate you can log into AAP, add a test Project, Inventory, and run a trivial Job Template with a default EE.
---
### Build & register your custom EE
Define an execution-environment spec that includes:

Collections you need (your usual automation stack).

Python packages for your chosen external DB and HTTP posting (e.g., pymongo for MongoDB; requests/httpx; or JDBC/psycopg2 if using Postgres).

An ansible.cfg snippet to enable a callback plugin (if choosing the callback route).

Build with ansible-builder (on your workstation or a CI runner), push the image to the OpenShift internal registry, and create a pull secret in AAP’s namespace if needed.

In AAP UI → Execution Environments, register the image and set it on your Job Templates as default.

---
### Stand up the external database
- MongoDB (MVP):
- Install the MongoDB/K8s Operator (Community or Enterprise) and create a StatefulSet with persistent volumes.
- Create a DB (automation) and collections: jobs, events, and optionally hosts.
- Create a DB user/secret and NetworkPolicy to limit access to your ingestion and webapp pods.
- Plan indexes (examples in #7).

---
### Choose and deploy the real-time ingestion path

Pick A (no app code) or B (more control). Keep C as fallback.

A) AAP External Logging → Fluent Bit/Logstash → DB

Deploy Fluent Bit (or Logstash) as a Service inside the cluster to receive events.

In AAP Settings → Logging, enable External Logging:

Point host/port/protocol to your collector Service.

Set structured JSON output (so you get per-line JSON job events).

Scope loggers to include job events (controller, task system, runner).

In Fluent Bit/Logstash:

Input: TCP/UDP/HTTP receiver for AAP logs.

Parse: Treat lines as JSON; normalize fields (job_id, template_id, inventory, project, play, task, host, status, start/finish timestamps, stdout).

Output: Write to the external DB (e.g., Logstash mongodb output, or Fluent Bit → HTTP to a small writer, or Fluent Bit es output if using Elasticsearch).

Benefit: No changes to playbooks; consistent, controller-wide stream.

B) EE Callback Plugin → Ingest API → DB

In your EE image, enable an Ansible callback plugin that POSTs each event to an HTTP endpoint (e.g., a minimal Ingest API running in OpenShift).

Deploy the Ingest API (tiny service) with:

Endpoints to receive event JSON.

DB client to upsert jobs and append events.

Optional queue (Redis/NATS/Kafka) for burst handling.

In AAP:

Set environment variables or ansible.cfg for the callback URL and auth.

Tie the custom EE to the Job Templates that you want streamed.

Benefit: Granular control (per template), easy to enrich/transform, independent of AAP’s logging settings.

C) Pull from AAP API (lowest lift, not push)

The web backend periodically polls AAP’s /api/v2/jobs/ and /api/v2/jobs/{id}/events/ and writes to the DB.

Simpler to start, but less “real-time” and adds API load. Good as a minimal fallback.

---
5) Web app (backend + UI) on OpenShift

Backend service (containerized) that:

Reads from the external DB.

Exposes REST endpoints (list jobs, job detail, host breakdown).

Pushes real-time updates to the UI via WebSockets or SSE.

MongoDB path: Use Change Streams on jobs/events to broadcast updates immediately.

Frontend UI (your choice: Streamlit/React/etc.):

Main grid: Job ID, Template, Started, Duration, Overall Status, #Hosts OK/FAILED/SKIPPED, and a progress indicator for running jobs.

Detail view: Play/task timeline and per-host results; live tail of stdout.

Filters: by template, inventory, status, owner, date range; quick search.

Expose via Service + Route. Store secrets for DB and (if used) Kafka/Redis in K8s Secrets. Lock down with NetworkPolicies.

---
6) Wire it all together (first working slice)

Confirm AAP jobs run with the custom EE.

Enable your chosen ingestion (A or B).

Run a sample job; verify:

AAP internal UI shows events (as before).

External DB receives events in near real-time.

Web app shows the new job and live updates.

Validate out-of-order and retry behavior (net hiccups, restarts).

---

7) Suggested external DB data model & indexing (MongoDB example)

Collection: jobs (one doc per job id)

Keys: job_id (unique), template_id, template_name, launch_user, inventory, project, status (pending|running|successful|failed|canceled), started_at, finished_at, duration_sec, total_hosts, ok, failed, skipped, unreachable, changed, extra_vars_summary.

Indexes: { job_id: 1 } (unique), { template_id: 1, started_at: -1 }, { status: 1, started_at: -1 }.

Collection: events (append-only)

Keys: job_id, counter, created, event (e.g., runner_on_ok, playbook_on_task_start), play, task, host, stdout, res (structured result), event_data (raw), level.

Indexes: { job_id: 1, counter: 1 } (compound), { created: -1 } (TTL optional for retention).

Collection: hosts (optional aggregated)

Keys: job_id, host, status, ok_count, changed_count, failed_count, skipped_count, unreachable_count, last_task.

Indexes: { job_id: 1, host: 1 }.

Retention: TTL index on events to auto-expire raw events after N days while keeping jobs summaries.

---
8) Security, governance, and SRE bits

TLS everywhere: Routes with re-encrypt; AAP external logging over TLS if supported by your collector; callback HTTPS for option B.

Secrets management: DB creds, callback tokens in K8s Secrets; mount as env vars.

RBAC/Least privilege: Separate namespaces (aap, aap-data, aap-ui), scoped ServiceAccounts.

NetworkPolicy: Only allow AAP → collector/ingest; ingest → DB; webapp → DB.

Resource sizing:

MongoDB/PG: start 4–8 GiB RAM, PVC 50–200 GiB (depends on retention).

Logstash/Fluent Bit: 0.5–2 CPU, 1–4 GiB RAM.

Webapp: small (0.5 CPU/512 MiB) and scale as needed.

Observability:

Expose AAP metrics and scrape with cluster Prometheus for job counts/durations.

Collector and DB dashboards (Grafana).

Backups: DB snapshots via Operator; AAP config export (Organizations, Templates, Credentials).

Retention & cleanup: CronJobs to compact/expire events; keep jobs summaries long-term.

---
9) Milestone checklist (use this to track progress)

SNO ready (storage, registry, routes).

AAP Operator installed; Controller healthy; sample job runs.

Custom EE built, pushed, and set on a template.

External DB deployed and reachable from inside cluster.

Ingestion path (A or B) deployed and verified with one job.

Web backend shows job list via REST; live updates working (WS/SSE).

UI renders jobs & detail pages; filters functional.

Security (TLS/Secrets/NetworkPolicies) locked down.

Retention/backup strategy in place.

Run real workloads; tune indexing and resource requests.

---

Bill of materials (components you’ll need)

OpenShift: SNO cluster, StorageClass, internal image registry, Operators (AAP, your DB Operator, optional Logstash/Fluent Bit/AMQ Streams).

AAP: Controller, Projects, Inventories, Credentials, Execution Environment (custom), Job Templates.

Custom EE image: Base EE + required Ansible Collections + Python libs (pymongo/psycopg2 or Elasticsearch client) + callback config (if using B).

External DB: MongoDB/PG/Elastic with persistent storage and backup/restore.

Collector (if using A): Fluent Bit or Logstash as a Service inside the cluster.

Ingest API (if using B): Lightweight containerized service.

Web app: Backend (REST + WS/SSE) + UI, both deployed on OpenShift with Routes.

Security/ops: Secrets, ConfigMaps, NetworkPolicies, RBAC, monitoring, backups.

Recommendations to start fast

Start with Option A (AAP External Logging → Fluent Bit/Logstash → MongoDB): zero changes to playbooks, strong real-time, no custom app in the middle.

Use MongoDB Change Streams in the web backend for instant UI updates.

Keep events short-lived (e.g., 7–14 days TTL) and retain jobs summaries longer.

If you want, I can turn this into a printable runbook (or a canvas you can iterate on) and map each step to specific OpenShift objects (CR names, Secrets, Routes, etc.).
