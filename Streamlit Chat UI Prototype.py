# Here’s a simple working Streamlit UI that connects to the FastAPI API
# Features:
# Simple chat-like controls for patching tasks.
# Calls the FastAPI backend endpoints (/run, /status, /finalize).
# Displays status and file paths.

# streamlit_ui.py
import streamlit as st
import requests

API_BASE = "http://patch-agent-api:8000"  # Internal OpenShift Service URL (or Route URL)

st.title("Linux Patching Assistant (POC)")
st.write("Choose an operation to run via Ansible Automation Platform:")

operation = st.selectbox("Select Task", ["Pre-check", "Apply+Reboot", "Post-check"])
wave = st.number_input("Enter Wave Number (1-4)", min_value=1, max_value=4, value=1)

if st.button("Run Task"):
    task_map = {
        "Pre-check": "pre-check",
        "Apply+Reboot": "apply-reboot",
        "Post-check": "post-check"
    }
    data = {"template_name": task_map[operation], "wave": wave}
    try:
        res = requests.post(f"{API_BASE}/run", json=data, timeout=10)
        if res.status_code == 200:
            job_id = res.json().get("job_id")
            st.success(f"Job launched successfully! Job ID: {job_id}")
            st.session_state['job_id'] = job_id
        else:
            st.error(f"Error: {res.text}")
    except Exception as e:
        st.error(f"Failed to call API: {e}")

if 'job_id' in st.session_state:
    st.subheader(f"Check Status for Job ID {st.session_state['job_id']}")
    if st.button("Check Status"):
        try:
            res = requests.get(f"{API_BASE}/status/{st.session_state['job_id']}", timeout=10)
            if res.status_code == 200:
                status = res.json().get("status")
                st.info(f"Status: {status}")
            else:
                st.error(f"Error: {res.text}")
        except Exception as e:
            st.error(f"Error: {e}")

    if st.button("Download Results"):
        try:
            res = requests.post(f"{API_BASE}/finalize/{st.session_state['job_id']}", timeout=30)
            if res.status_code == 200:
                success_file = res.json().get("success_file")
                failure_file = res.json().get("failure_file")
                st.success("Reports generated successfully!")
                st.write(f"✅ Success File: {success_file}")
                st.write(f"❌ Failure File: {failure_file}")
            else:
                st.error(f"Error: {res.text}")
        except Exception as e:
            st.error(f"Error: {e}")
