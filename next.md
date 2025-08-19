FastAPI Service (Patching Brain)

This service exposes endpoints for your AI/UX to call. It handles Tekton pipeline runs and streams logs.
```py
# app/main.py
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from kubernetes import client, config
import asyncio

app = FastAPI(title="Patching Brain API")

# Load in-cluster K8s config (works inside OpenShift pod)
config.load_incluster_config()
tekton = client.CustomObjectsApi()

NAMESPACE = "patching-ai"

class PatchRequest(BaseModel):
    action: str         # "precheck" | "stage" | "apply" | "reboot" | "postcheck"
    group: str          # Host group (AAP inventory group)
    kernel: str = None  # Desired kernel (optional, only for apply)

@app.post("/patch")
def run_patch(req: PatchRequest):
    """Trigger Tekton pipeline with params."""
    body = {
        "apiVersion": "tekton.dev/v1beta1",
        "kind": "PipelineRun",
        "metadata": {"generateName": f"patch-{req.action}-"},
        "spec": {
            "pipelineRef": {"name": "patching-pipeline"},
            "params": [
                {"name": "action", "value": req.action},
                {"name": "group", "value": req.group},
                {"name": "kernel", "value": req.kernel or ""},
            ]
        }
    }
    pr = tekton.create_namespaced_custom_object(
        group="tekton.dev", version="v1beta1",
        namespace=NAMESPACE, plural="pipelineruns", body=body
    )
    return {"status": "ok", "pipelineRun": pr["metadata"]["name"]}

@app.websocket("/logs/{pr_name}")
async def stream_logs(ws: WebSocket, pr_name: str):
    """Stream Tekton TaskRun logs over websocket."""
    await ws.accept()
    core = client.CoreV1Api()
    while True:
        pods = core.list_namespaced_pod(NAMESPACE, label_selector=f"tekton.dev/pipelineRun={pr_name}")
        for pod in pods.items:
            try:
                log = core.read_namespaced_pod_log(
                    pod.metadata.name, NAMESPACE, container="step-ansible"
                )
                await ws.send_text(log)
            except Exception:
                pass
        await asyncio.sleep(5)
```

Tiny React Chat Panel

Simple frontend for chatting with the patching brain.
```py
// src/App.jsx
import { useState } from "react";
import { Button } from "@/components/ui/button";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const send = async () => {
    const res = await fetch("/patch", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        action: input, group: "prod-web", kernel: "5.14.0-427.16.1.el9"
      })
    });
    const data = await res.json();
    setMessages([...messages, {role: "user", text: input}, {role: "system", text: JSON.stringify(data)}]);
    setInput("");
  };

  return (
    <div className="flex flex-col items-center p-4">
      <div className="w-full max-w-xl border rounded-2xl p-4 bg-white shadow">
        <div className="h-96 overflow-y-auto mb-4">
          {messages.map((m, i) => (
            <div key={i} className={`my-2 ${m.role==="user"?"text-blue-600":"text-gray-700"}`}>
              {m.text}
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded p-2"
            value={input}
            onChange={(e)=>setInput(e.target.value)}
            placeholder="Type: stage | apply | reboot | precheck | postcheck"
          />
          <Button onClick={send}>Send</Button>
        </div>
      </div>
    </div>
  );
}
```

Example AAP Job Templates & Vars

You’ll need 5 job templates in AAP (one per action).
Each template should accept survey variables:

Survey Variables (common across templates)
```yaml
- variable: group
  type: text
  question: "Target Inventory Group"
  required: true

- variable: kernel
  type: text
  question: "Desired Kernel (only for apply)"
  required: false
```
Template Mapping
- Precheck → Playbook: precheck.yml (no credentials needed)
- Stage → Playbook: stage.yml (AAP credentials required)
- Apply → Playbook: apply.yml (AAP credentials required, uses kernel)
- Reboot → Playbook: reboot.yml (AAP credentials required)
- Postcheck → Playbook: postcheck.yml (no credentials needed)

This gives you:
- FastAPI backend → Tekton → AAP
- React chat → talk to FastAPI
- AAP job templates with expected survey vars

Would you like me to bundle all these into Kubernetes YAML (Deployment + Service + Route) so you can directly oc apply -f and have the FastAPI + React UI running on your OpenShift cluster?
