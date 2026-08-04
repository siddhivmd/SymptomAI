import os
import sys
import json
import logging

# FastAPI Backend using Groq Llama-3.3-70b-versatile
sys.path.insert(0, os.path.dirname(__file__))

from typing import List, Dict, Any, Optional, Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from models import (
    Conversation, AgentResponse, PromptArm, ChatMessage, Message,
    ClinicalCase, EvalSummary, DDxResult, DDxItem
)
from llm_client import LLMClient
from agents import BaseAgent, StructuredAgent, DynamicAgent
from agents.base_prompt import SYSTEM_PROMPT as BASE_PROMPT
from agents.structured_prompt import SYSTEM_PROMPT as STRUCTURED_PROMPT
from agents.dynamic_prompt import SYSTEM_PROMPT as DYNAMIC_PROMPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("symptomcheck_api")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="SymptomCheck-Mini API",
    description="FastAPI Backend for AI Clinical Symptom Checking & Differential Diagnosis Benchmark",
    version="1.0.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize LLM Client and Agents
llm_client = LLMClient()
agents = {
    PromptArm.BASE: BaseAgent(llm_client),
    PromptArm.STRUCTURED: StructuredAgent(llm_client),
    PromptArm.DYNAMIC: DynamicAgent(llm_client)
}

SYSTEM_PROMPTS = {
    "base": BASE_PROMPT,
    "structured": STRUCTURED_PROMPT,
    "dynamic": DYNAMIC_PROMPT
}

# In-memory storage for active demo sessions
sessions: Dict[str, Conversation] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str
    prompt_arm: PromptArm = PromptArm.BASE
    patient_age: Optional[int] = 42
    patient_gender: Optional[str] = "Female"

class ChatInputPayload(BaseModel):
    arm: Literal["base", "structured", "dynamic"] = "base"
    messages: List[Message]

class ChatOutputPayload(BaseModel):
    message: str
    complete: bool
    ddx_result: Optional[DDxResult] = None

@app.get("/")
@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health-check endpoint returning server status."""
    return {"status": "ok", "system": "SymptomCheck-Mini", "mock_mode": llm_client.use_mock}

@app.post("/chat", response_model=ChatOutputPayload)
@limiter.limit("10/minute")
async def chat_endpoint(request: Request, payload: ChatInputPayload):
    """
    POST /chat: Selects prompt by arm, calls GeminiClient.generate(),
    returns assistant message and 'complete' flag if valid DDx JSON is returned.
    """
    system_prompt = SYSTEM_PROMPTS.get(payload.arm, BASE_PROMPT)
    messages_dicts = [m.model_dump() for m in payload.messages]

    response_text = await llm_client.generate(
        system_prompt=system_prompt,
        messages=messages_dicts
    )

    complete = False
    ddx_res = None

    try:
        cleaned_text = response_text.strip()
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

        data = json.loads(cleaned_text)
        if isinstance(data, dict) and "differential" in data:
            ddx_res = DDxResult.model_validate(data)
            complete = True
    except Exception:
        complete = False
        ddx_res = None

    return ChatOutputPayload(
        message=response_text,
        complete=complete,
        ddx_result=ddx_res
    )

@app.post("/api/chat", response_model=AgentResponse)
def process_chat(req: ChatRequest):
    """
    Process patient chat input using specified prompt strategy arm (legacy endpoint).
    """
    if req.session_id not in sessions:
        sessions[req.session_id] = Conversation(
            session_id=req.session_id,
            prompt_arm=req.prompt_arm,
            messages=[],
            patient_age=req.patient_age,
            patient_gender=req.patient_gender
        )

    conv = sessions[req.session_id]
    conv.messages.append(Message(role="patient", content=req.message))

    agent = agents.get(req.prompt_arm, agents[PromptArm.BASE])

    try:
        response = agent.run(
            history=conv.messages,
            patient_age=conv.patient_age or 40,
            patient_gender=conv.patient_gender or "Unspecified"
        )

        conv.messages.append(Message(
            role="assistant",
            content=f"Differential: {[d.condition_name for d in response.differential_diagnosis]}. Rationale: {response.clinical_rationale}"
        ))

        return response
    except Exception as e:
        logger.error(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cases", response_model=List[ClinicalCase])
def get_synthetic_cases():
    """Return synthetic clinical benchmark cases."""
    cases_path = os.path.join(os.path.dirname(__file__), "..", "eval", "synthetic_cases.json")
    if not os.path.exists(cases_path):
        raise HTTPException(status_code=404, detail="Synthetic cases dataset not found")

    with open(cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [ClinicalCase(**item) for item in data]

@app.delete("/api/session/{session_id}")
def reset_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "reset", "session_id": session_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
