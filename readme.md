# AI Patching Orchestrator on OpenShift (Single‑Node, OpenShift AI)

This guide packages a production‑like POC that runs on a **single‑node OpenShift** cluster and integrates with **Ansible Automation Platform (AAP)** and **OpenShift AI** (formerly RHODS). It implements:

- Natural‑language **commands** to drive patching phases: `precheck`, `stage`, `apply`, `reboot`, `postcheck` (group‑scoped).  
- **Credential gating**: AAP creds are **only** required for `stage/apply/reboot`.  
- Minimal response style: **OK** on success; **downloadable logs** on failure.  
- **Knowledge base** for error classification → suggested remediations, and history/Q&A.  

---

## 0) Prereqs (single node)
- OpenShift 4.14+ SNO with 8+ vCPUs, 32–64GB RAM.  
- Operators: **OpenShift AI**, **Pipelines (Tekton)**, **Serverless (Knative, optional for model serving)**.  
- AAP reachable from cluster (AAP controller API URL) and a technical account for automation.
- (Optional GPU) for on‑cluster LLM; otherwise use CPU‑friendly small model or external API.

---

## 1) High‑Level Architecture

```
+------------------------------  Single Node OpenShift  ------------------------------+
|                                                                                    |
|  [Route]  ──>  Chat UI (frontend)  ──calls──>  FastAPI “Patching Brain” (Backend)  |
|                                                |      |                            |
|                                                |      +--> Postgres (history,      |
|                                                |             incidents, runs)      |
|                                                |                                   |
|                                                +--> Tekton Pipelines (pre/stage/   |
|                                                        apply/reboot/post tasks)    |
|                                                               |                    |
|                                                               +--> AAP API (run    |
|                                                                    templates)      |
|                                                                                    |
|  [Model Serving via OpenShift AI]  <──>  RAG/LLM (error explain, Q&A, SOPs)        |
|                                                                                    |
+------------------------------------------------------------------------------------+
```

**Key principles**
- **Read‑only phases** (pre/post) → Tekton tasks that do discovery & verification (no AAP creds).  
- **Change phases** (stage/apply/reboot) → Tekton tasks that call **AAP** using a secret (only mounted when needed).  
- **FastAPI** exposes REST endpoints consumed by Chat UI + serves downloadable logs.  
- **LLM** provides answers/explanations over indexed run logs + SOPs (RAG).  

---

## 2) Namespaces & Access
- Project/namespace: `patching-poc`
- ServiceAccount: `patch-bot`
- RBAC: SA can create Tekton `PipelineRun` & read `Pods/Logs` in the project.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: patching-poc
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: patch-bot
  namespace: patching-poc
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: patch-bot-role
  namespace: patching-poc
rules:
  - apiGroups: ["tekton.dev"]
    resources: ["pipelineruns","taskruns"]
    verbs: ["create","get","list","watch"]
  - apiGroups: [""]
    resources: ["pods","pods/log","events","configmaps","secrets"]
    verbs: ["get","list","watch","create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: patch-bot-rb
  namespace: patching-poc
subjects:
  - kind: ServiceAccount
    name: patch-bot
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: patch-bot-role
```

---

## 3) Configuration & Secrets

**ConfigMap** (endpoints, behavior)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: patch-config
  namespace: patching-poc
data:
  AAP_URL: "https://aap.example.com"
  INVENTORY_GROUP_FIELD: "patch_group"
  LOG_RETENTION_DAYS: "30"
```

**Secrets** (only mounted by change‑tasks)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aap-credentials
  namespace: patching-poc
type: Opaque
stringData:
  username: "<aap-user>"
  password: "<aap-pass>"
```
> The FastAPI never stores creds persistently; it injects them into the **Tekton run** only when user requests `stage/apply/reboot`.

**Database** (Postgres – can be a Deployment/StatefulSet or an Operator‑managed cluster)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pg
  namespace: patching-poc
spec:
  replicas: 1
  selector: { matchLabels: { app: pg } }
  template:
    metadata: { labels: { app: pg } }
    spec:
      containers:
        - name: postgres
          image: postgres:15
          env:
            - { name: POSTGRES_DB, value: patchdb }
            - { name: POSTGRES_USER, value: patch }
            - { name: POSTGRES_PASSWORD, value: patchpass }
          ports: [{ containerPort: 5432 }]
          volumeMounts:
            - { name: data, mountPath: /var/lib/postgresql/data }
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: pg
  namespace: patching-poc
spec:
  selector: { app: pg }
  ports:
    - name: db
      port: 5432
      targetPort: 5432
```

---

## 4) FastAPI “Patching Brain”
Features:
- REST: `/api/run/precheck|stage|apply|reboot|postcheck`  
- Minimal responses: `{"status":"OK"}` or `{"status":"ERROR","log_url":"..."}`  
- Log store in Postgres (large logs written to object store like S3/NooBaa/MinIO if available).  
- Triggers Tekton PipelineRuns with **param set** (group, desired kernel, etc.).  

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: patch-brain
  namespace: patching-poc
spec:
  replicas: 1
  selector: { matchLabels: { app: patch-brain } }
  template:
    metadata: { labels: { app: patch-brain } }
    spec:
      serviceAccountName: patch-bot
      containers:
        - name: api
          image: ghcr.io/example/patch-brain:latest # build your image
          env:
            - { name: DB_DSN, value: postgresql://patch:patchpass@pg:5432/patchdb }
            - { name: AAP_URL, valueFrom: { configMapKeyRef: { name: patch-config, key: AAP_URL } } }
          ports: [{ containerPort: 8080 }]
---
apiVersion: v1
kind: Service
metadata:
  name: patch-brain
  namespace: patching-poc
spec:
  selector: { app: patch-brain }
  ports:
    - port: 80
      targetPort: 8080
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: patch-brain
  namespace: patching-poc
spec:
  to:
    kind: Service
    name: patch-brain
  tls:
    termination: edge
```

**Minimal API behavior (pseudo‑Python)**
```
POST /api/run/precheck   {group: 4}      → creates PipelineRun(pr: precheck)  → poll → OK or ERROR + log_url
POST /api/run/stage      {group: 4}      → requires AAP creds; PR mounts aap-credentials → OK/ERROR
POST /api/run/apply      {group: 4}      → requires AAP creds; PR mounts aap-credentials → OK/ERROR
POST /api/run/reboot     {group: 4}      → requires AAP creds; PR mounts aap-credentials → OK/ERROR
POST /api/run/postcheck  {group: 4}      → no creds; PR runs validations → OK/ERROR
```

---

## 5) Tekton Pipelines & Tasks
We define **five Tasks** and a single **Pipeline** that switches by param `phase`.

**Shared Params**
- `group` (int/string) – the patch group (from inventory var)  
- `desired_kernel` (string) – your saved template variable used by AAP  
- `phase` (enum) – `precheck|stage|apply|reboot|postcheck`

### 5.1 Tasks

**Task: precheck (no creds)**
- Validates: kernel availability on Satellite, repo health, space on `/usr,/boot,/var,/` via SSH/Ansible ad‑hoc EE read‑only.
- Writes a concise JSON summary and a **full log file** to a PVC (or S3).

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: precheck
  namespace: patching-poc
spec:
  params:
    - name: group
      type: string
  workspaces:
    - name: logs
  steps:
    - name: run
      image: quay.io/ansible/ansible-runner:stable-2.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        echo "Precheck group: $(params.group)" | tee $(workspaces.logs.path)/precheck-$(params.group).log
        # run ansible ad-hoc or playbook in check mode against inventory limited to the group
        # collect: free space, repos, available kernel, satellite status
        # write JSON summary to logs as well
```

**Task: aap-run (generic invoker for stage/apply/reboot)**
- Calls AAP Job Template via REST with inventory limit to `group`.  
- **Mounts `aap-credentials` secret**; not used by pre/post tasks.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: aap-run
  namespace: patching-poc
spec:
  params:
    - name: template
    - name: group
    - name: desired_kernel
  workspaces:
    - name: logs
  steps:
    - name: invoke
      image: registry.access.redhat.com/ubi9/python-39
      env:
        - name: AAP_URL
          valueFrom:
            configMapKeyRef: { name: patch-config, key: AAP_URL }
        - name: AAP_USER
          valueFrom:
            secretKeyRef: { name: aap-credentials, key: username }
        - name: AAP_PASS
          valueFrom:
            secretKeyRef: { name: aap-credentials, key: password }
      script: |
        #!/usr/bin/env python3
        import os,sys,requests,json
        url=os.environ['AAP_URL'].rstrip('/')+"/api/v2/job_templates/"+sys.argv[1]+"/launch/"
        body={
          "extra_vars":{
            "desired_kernel": sys.argv[3],
            "patch_group": sys.argv[2]
          }
        }
        r=requests.post(url,auth=(os.environ['AAP_USER'],os.environ['AAP_PASS']),json=body,timeout=60)
        open("$(workspaces.logs.path)/"+sys.argv[1]+"-"+sys.argv[2]+".log","w").write(r.text)
        r.raise_for_status()
      args: ["$(params.template)","$(params.group)","$(params.desired_kernel)"]
```

**Task: postcheck (no creds)**
- Verifies `uname -r == desired` and basic service probes by role.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: postcheck
  namespace: patching-poc
spec:
  params:
    - name: group
      type: string
  workspaces:
    - name: logs
  steps:
    - name: verify
      image: quay.io/ansible/ansible-runner:stable-2.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        echo "Postcheck group $(params.group)" | tee $(workspaces.logs.path)/postcheck-$(params.group).log
        # run checks and write detailed log
```

### 5.2 Pipeline
```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: patch-orchestrator
  namespace: patching-poc
spec:
  params:
    - name: phase
    - name: group
    - name: desired_kernel
  workspaces:
    - name: logs
  tasks:
    - name: precheck
      when: [{input: "$(params.phase)", operator: In, values: ["precheck"]}]
      taskRef: { name: precheck }
      params: [{ name: group, value: "$(params.group)" }]
      workspaces: [{ name: logs, workspace: logs }]
    - name: stage
      when: [{input: "$(params.phase)", operator: In, values: ["stage"]}]
      taskRef: { name: aap-run }
      params:
        - { name: template, value: "STAGE_TEMPLATE_ID" }
        - { name: group, value: "$(params.group)" }
        - { name: desired_kernel, value: "$(params.desired_kernel)" }
      workspaces: [{ name: logs, workspace: logs }]
    - name: apply
      when: [{input: "$(params.phase)", operator: In, values: ["apply"]}]
      taskRef: { name: aap-run }
      params:
        - { name: template, value: "APPLY_TEMPLATE_ID" }
        - { name: group, value: "$(params.group)" }
        - { name: desired_kernel, value: "$(params.desired_kernel)" }
      workspaces: [{ name: logs, workspace: logs }]
    - name: reboot
      when: [{input: "$(params.phase)", operator: In, values: ["reboot"]}]
      taskRef: { name: aap-run }
      params:
        - { name: template, value: "REBOOT_TEMPLATE_ID" }
        - { name: group, value: "$(params.group)" }
        - { name: desired_kernel, value: "$(params.desired_kernel)" }
      workspaces: [{ name: logs, workspace: logs }]
    - name: postcheck
      when: [{input: "$(params.phase)", operator: In, values: ["postcheck"]}]
      taskRef: { name: postcheck }
      params: [{ name: group, value: "$(params.group)" }]
      workspaces: [{ name: logs, workspace: logs }]
```

**PipelineRun (created by FastAPI)**
```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: patch-orchestrator-
spec:
  pipelineRef: { name: patch-orchestrator }
  params:
    - { name: phase, value: "precheck" }           # or stage/apply/reboot/postcheck
    - { name: group, value: "5" }
    - { name: desired_kernel, value: "5.14.0-503.14.1.el9_4" }
  workspaces:
    - name: logs
      volumeClaimTemplate:
        spec:
          accessModes: [ReadWriteOnce]
          resources:
            requests: { storage: 1Gi }
```

---

## 6) Chat UI Commands (minimal)
- `Precheck group 5` → POST `/api/run/precheck {group:5}` → returns `{status:OK}` or `{status:ERROR, log_url}`
- `Stage patch to group 5` → POST `/api/run/stage {group:5}` (prompts for AAP creds) → OK/ERROR
- `Apply patch to group 5` → POST `/api/run/apply {group:5}` (prompts creds) → OK/ERROR
- `Reboot group 5` → POST `/api/run/reboot {group:5}` (prompts creds) → OK/ERROR
- `Postcheck group 5` → POST `/api/run/postcheck {group:5}` → OK/ERROR

**Downloadable logs**: the API returns a signed URL (or `/api/logs/<id>`) that streams the Tekton Task log or stored artifact.

---

## 7) OpenShift AI (LLM) Integration
Two viable paths on SNO:
1) **Lightweight local model** (CPU OK): e.g., 3–8B instruction model served via **KServe** or a simple Deployment + Route.  
2) **External model API**: keep logic identical; swap inference URL.

**Example (custom Deployment for vLLM‑style server)**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm
  namespace: patching-poc
spec:
  replicas: 1
  selector: { matchLabels: { app: llm } }
  template:
    metadata: { labels: { app: llm } }
    spec:
      containers:
        - name: server
          image: ghcr.io/example/tiny-llm-server:latest
          env:
            - { name: MODEL_NAME, value: mistral-7b-instruct-q4 }
          ports: [{ containerPort: 8000 }]
---
apiVersion: v1
kind: Service
metadata:
  name: llm
  namespace: patching-poc
spec:
  selector: { app: llm }
  ports: [{ port: 80, targetPort: 8000 }]
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: llm
  namespace: patching-poc
spec:
  to: { kind: Service, name: llm }
```

**RAG data sources**
- Postgres tables: `runs`, `incidents`, `facts`, `qa`
- Your SOPs/KB (mounted ConfigMaps or object storage)  
- Embeddings + vector index (e.g., `pgvector` extension in Postgres or an in‑memory FAISS for POC)

---

## 8) AAP Templates (assumed)
- `STAGE_TEMPLATE_ID`: dnf download/cache exact kernel NEVRA for hosts in `group` (T‑24h).  
- `APPLY_TEMPLATE_ID`: install kernel packages only (no reboot).  
- `REBOOT_TEMPLATE_ID`: orchestrated reboot + pre/post drain/undrain hooks per role.  
- All templates accept **`patch_group`** and **`desired_kernel`** survey vars.

---

## 9) Security Model
- **Pre/Post** tasks run without AAP creds.  
- **Stage/Apply/Reboot** mount `aap-credentials` secret into task pod **only** during that task.  
- FastAPI never persists credentials; it only references the secret name to include in the TaskRun env.  
- Optionally add **sealed‑secrets** or External Secrets Operator.

---

## 10) Operational Tips
- Add PVC or S3 to store logs beyond PipelineRun lifecycle; expose via `/api/logs`.
- Tag PipelineRuns with labels: `phase`, `group`, `kernel`.  
- Grafana dashboard with Tekton and custom app metrics (success rate, MTTR, failures by error code).  
- Implement **error taxonomy** (`E-REPO-EMPTY`, `E-DISK-BOOT`, `E-LOCK-DNF`, `E-SAT-ENTITLE`, `E-PKG-CONFLICT`, `E-KERNEL-MISSING`, `E-POST-SERVICE`).  
- Map each error → **approved remediation** AAP template for later auto‑fix.

---

## 11) Example API Contract (FastAPI)
```
POST /api/run/{phase}
{ "group": 5, "desired_kernel": "5.14.0-503.14.1.el9_4" }
→ { "status": "OK" }
→ { "status": "ERROR", "log_url": "https://route/logs/abc123" }

GET  /api/host/{hostname}   → current state & last results (for Q&A)
GET  /api/history?group=5   → last N runs by phase
GET  /api/logs/{id}         → stream/download log artifact
```

---

## 12) Step‑by‑Step Bring‑Up
1. Create `patching-poc` namespace, SA, RBAC.  
2. Deploy Postgres, then `patch-brain` (FastAPI) and expose a Route.  
3. Create Tekton **Tasks** and **Pipeline** above.  
4. Create the `aap-credentials` secret; **do not** mount it in pre/post tasks.  
5. Wire FastAPI to create PipelineRuns per phase and poll status → return OK or `log_url`.  
6. (Optional) Deploy small LLM service and index your SOPs + previous runs for Q&A.  
7. Build a tiny web Chat UI or use `oc port-forward` + curl to test flows.  

---

## 13) Test Scenarios (what “OK” looks like)
- `POST /api/run/precheck {group:3}` → `{"status":"OK"}`
- `POST /api/run/stage {group:3}` → prompts UI for creds (or references secret) → `{"status":"OK"}`
- If any failure: `{"status":"ERROR","log_url":"…/logs/xyz"}` (click to download full Tekton step log)

---

## 14) What to add next
- Auto‑remediation gates: allow a subset of hosts to run approved fixes.  
- pgvector for similarity search across incidents → smarter suggestions.  
- ServiceNow integration: open/update change/tasks with run links + artifact URLs.  
- SSO via OpenShift OAuth or Keycloak for the Chat UI and API.

---

**You now have a complete POC blueprint** tailored for SNO + OpenShift AI. Drop these manifests in `kustomize/` or `helm/`, build the `patch-brain` image, and you’re ready to iterate.

