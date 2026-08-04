import os
import sys
import json
import random
import httpx
import pandas as pd
import streamlit as st

# Ensure backend imports work for models & prompts
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models import Message, DDxResult
from llm_client import LLMClient
from agents.base_prompt import SYSTEM_PROMPT as BASE_PROMPT
from agents.structured_prompt import SYSTEM_PROMPT as STRUCTURED_PROMPT
from agents.dynamic_prompt import SYSTEM_PROMPT as DYNAMIC_PROMPT

SYSTEM_PROMPTS = {
    "base": BASE_PROMPT,
    "structured": STRUCTURED_PROMPT,
    "dynamic": DYNAMIC_PROMPT
}

# Backend API endpoint configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000/chat")

# Page configuration
st.set_page_config(
    page_title="SymptomCheck-Mini Demo",
    page_icon="🩺",
    layout="wide"
)

st.title("🩺 SymptomCheck-Mini Demo")
st.caption("AI Clinical Symptom Checker & Benchmark Strategy Evaluation")

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "assigned_arm" not in st.session_state:
    st.session_state.assigned_arm = "base"
if "ddx_complete" not in st.session_state:
    st.session_state.ddx_complete = False
if "latest_ddx" not in st.session_state:
    st.session_state.latest_ddx = None

@st.cache_resource
def get_llm_client():
    return LLMClient()

def check_backend_health():
    """Check if FastAPI backend server is accessible."""
    try:
        health_url = BACKEND_URL.replace("/chat", "/health")
        res = httpx.get(health_url, timeout=2.0)
        return res.status_code == 200
    except Exception:
        return False

server_online = check_backend_health()

# Sidebar Controls
with st.sidebar:
    st.header("Settings & Controls")
    
    arm_choice = st.selectbox(
        "Select Prompting Arm:",
        options=["random", "base", "structured", "dynamic"],
        index=0,
        help="Select an arm or 'random' to mirror the paper's trial randomization."
    )
    
    if st.button("🔄 Reset Consultation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.ddx_complete = False
        st.session_state.latest_ddx = None
        if arm_choice == "random":
            st.session_state.assigned_arm = random.choice(["base", "structured", "dynamic"])
        else:
            st.session_state.assigned_arm = arm_choice
        st.rerun()

    # Determine active arm if not set
    if arm_choice != "random":
        st.session_state.assigned_arm = arm_choice
    elif not st.session_state.assigned_arm or st.session_state.assigned_arm not in ["base", "structured", "dynamic"]:
        st.session_state.assigned_arm = random.choice(["base", "structured", "dynamic"])

    st.info(f"**Active Arm**: `{st.session_state.assigned_arm}`" + (" (Randomized)" if arm_choice == "random" else ""))
    
    if server_online:
        st.success(f"🟢 **API Endpoint**: `/chat` (`{BACKEND_URL}`)")
    else:
        st.warning(f"🟡 **API Server Offline**: Fallback Mode (`{BACKEND_URL}` unavailable)")
        
    st.caption("⚠️ Educational demo only. Not a medical device.")

# Navigation Tabs
tab_chat, tab_results = st.tabs(["💬 Consultation Chat", "📊 Evaluation Results"])

# TAB 1: CONSULTATION CHAT
with tab_chat:
    st.warning("⚠️ **PROMINENT MEDICAL DISCLAIMER**: This application is an open-source educational demo, NOT a medical device. It does NOT provide medical advice, diagnosis, or treatment. Always consult a licensed clinician for medical concerns.")
    st.subheader("Patient Consultation")
    
    # Display message history
    for msg in st.session_state.messages:
        role = msg.get("role", "user")
        with st.chat_message("user" if role in ["user", "patient"] else "assistant"):
            st.write(msg.get("content", ""))

    # Display completed DDx Result if available
    if st.session_state.ddx_complete and st.session_state.latest_ddx:
        st.success("✅ **Consultation Complete - Differential Diagnosis Generated**")
        ddx_data = st.session_state.latest_ddx
        
        st.markdown(f"**Clinical History Summary:** {ddx_data.get('history_summary')}")
        st.markdown("#### 📋 5-Item Differential Diagnosis")
        
        diff_list = ddx_data.get("differential", [])
        for idx, item in enumerate(diff_list, start=1):
            st.markdown(f"**{idx}. {item.get('diagnosis')}**")
            st.caption(f"Rationale: {item.get('rationale')}")
            
        st.warning(f"⚖️ **Disclaimer**: {ddx_data.get('disclaimer')}")

    # Input for new user message
    if not st.session_state.ddx_complete:
        user_input = st.chat_input("Describe your symptoms (e.g., 'I have a burning chest pain after eating spicy food')...")
        
        if user_input:
            st.session_state.messages.append({"role": "patient", "content": user_input})
            
            arm = st.session_state.assigned_arm
            payload = {
                "arm": arm,
                "messages": st.session_state.messages
            }
            
            with st.spinner("Analyzing symptoms via `/chat` endpoint..."):
                response_text = None
                complete = False
                ddx_data = None
                
                try:
                    res = httpx.post(BACKEND_URL, json=payload, timeout=30.0)
                    if res.status_code == 200:
                        data = res.json()
                        response_text = data.get("message", "")
                        complete = data.get("complete", False)
                        ddx_data = data.get("ddx_result")
                    else:
                        st.error(f"API Error ({res.status_code}): {res.text}")
                except Exception:
                    # Fallback to direct client call if backend server is offline
                    llm_client = get_llm_client()
                    system_prompt = SYSTEM_PROMPTS.get(arm, BASE_PROMPT)
                    
                    import asyncio
                    response_text = asyncio.run(
                        llm_client.generate(system_prompt=system_prompt, messages=st.session_state.messages)
                    )
                    
                    cleaned_text = response_text.strip()
                    if "```json" in cleaned_text:
                        cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in cleaned_text:
                        cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
                        
                    try:
                        parsed_json = json.loads(cleaned_text)
                        if isinstance(parsed_json, dict) and "differential" in parsed_json:
                            complete = True
                            ddx_data = parsed_json
                    except Exception:
                        complete = False

                if response_text:
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    if complete and ddx_data:
                        st.session_state.ddx_complete = True
                        st.session_state.latest_ddx = ddx_data
                        
            st.rerun()

# TAB 2: EVALUATION RESULTS
with tab_results:
    st.subheader("Benchmark Evaluation Results")
    
    png_path = os.path.join(os.path.dirname(__file__), "..", "eval", "results", "accuracy_by_arm.png")
    csv_path = os.path.join(os.path.dirname(__file__), "..", "eval", "results", "results.csv")
    
    col_chart, col_data = st.columns([1, 1])
    
    with col_chart:
        st.markdown("### Top-5 Accuracy & Error Bars (`accuracy_by_arm.png`)")
        if os.path.exists(png_path):
            st.image(png_path, use_container_width=True)
        else:
            st.info("Run `python eval/run_eval.py` to generate `accuracy_by_arm.png`.")
            
    with col_data:
        st.markdown("### Benchmark Results Table (`results.csv`)")
        if os.path.exists(csv_path):
            df_results = pd.read_csv(csv_path)
            st.dataframe(df_results, use_container_width=True)
            
            # Summary Metrics
            st.markdown("#### Summary Metrics by Strategy Arm")
            if "position" in df_results.columns:
                df_results["top1"] = (df_results["position"] == 1).astype(int)
                df_results["top5"] = ((df_results["position"] > 0) & (df_results["position"] <= 5)).astype(int)
                
                summary_df = df_results.groupby("arm").agg(
                    Total_Cases=("case_id", "count"),
                    Top1_Acc=("top1", lambda x: f"{x.mean()*100:.1f}%"),
                    Top5_Acc=("top5", lambda x: f"{x.mean()*100:.1f}%"),
                    Avg_Turns=("turn_count", "mean")
                )
                st.table(summary_df)
        else:
            st.info("Run `python eval/run_eval.py` to generate `results.csv`.")

