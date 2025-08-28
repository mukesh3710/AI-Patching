### Full POC
---
Below are ready-to-apply OpenShift YAML manifests for the full POC consisting of 3 Python components:
- patch-agent-api (FastAPI)
- streamlit-ui (Streamlit)
- kb-service (KB REST API)

All manifests assume a dedicated namespace patching. Replace image names, registry references, and the AAP token value before applying. Save this full text to a file (e.g. patching-poc-all.yaml) and run oc apply -f patching-poc-all.yaml after doing the token step shown below.
