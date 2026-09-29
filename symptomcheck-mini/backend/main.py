import os
import sys
import csv
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
    ClinicalCase, EvalSummary, DDxResult, DDxItem, PlainExplanation
)
from llm_client import LLMClient, SCAFFOLD_MODEL
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
    explanation: Optional[PlainExplanation] = None

PLAIN_LANGUAGE_PROMPT = """You rewrite a clinical differential diagnosis so a patient with no medical training can understand it.

Rules:
- Use short, everyday words (aim for a 12-year-old reading level). If a medical term is unavoidable, explain it in the same sentence.
- "plain_name" must be the name a non-medical person would use, never the clinical term itself.
  Examples: "Vulvovaginal candidiasis" -> "Yeast infection"; "Acute myocardial infarction" -> "Heart attack";
  "Gastroesophageal reflux disease" -> "Acid reflux"; "Chlamydial cervicitis" -> "Chlamydia (a sexually transmitted infection)".
  If there is no everyday name, describe it briefly (e.g. "Bacterial vaginosis" -> "Bacterial imbalance in the vagina").
- Keep the same conditions in the same order. Do not add, remove, or re-rank them, and do not invent new facts.
- For each condition, say in 1-2 sentences what it is and why it might fit the symptoms described.
- "next_steps": 2-3 sentences of general guidance on what kind of care to seek and how soon, including warning signs that mean getting help urgently. Do not prescribe medicines or doses.
- Be calm and non-alarming, but do not downplay serious possibilities.

Return only JSON in exactly this shape:
{"summary": "<1-2 sentences restating what the patient described, addressed to them as \"you\">",
 "items": [{"plain_name": "<everyday name>", "explanation": "<1-2 plain sentences>"}],
 "next_steps": "<2-3 plain sentences>"}"""


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse the outermost {...} so prose or code fences around the JSON don't break parsing."""
    start, end = text.find("{"), text.rfind("}")
    if not 0 <= start < end:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def explain_in_plain_language(ddx: DDxResult) -> Optional[PlainExplanation]:
    """Patient-friendly rewrite of the DDx. The arm prompts are left untouched so benchmark results stay comparable."""
    if llm_client.use_mock:
        return None
    clinical = json.dumps({
        "history_summary": ddx.history_summary,
        "differential": [{"diagnosis": d.diagnosis, "rationale": d.rationale} for d in ddx.differential],
    })
    text = await llm_client.generate(
        system_prompt=PLAIN_LANGUAGE_PROMPT,
        messages=[{"role": "user", "content": clinical}],
        model=SCAFFOLD_MODEL,
        max_tokens=700,
    )
    data = parse_json_object(text)
    if not data:
        logger.warning("Plain-language explanation could not be parsed; returning clinical DDx only.")
        return None
    try:
        explanation = PlainExplanation.model_validate(data)
    except Exception as e:
        logger.warning(f"Plain-language explanation failed validation: {e}")
        return None
    # Only trust item-by-item alignment when the model kept the same list length.
    if len(explanation.items) != len(ddx.differential):
        explanation.items = []
    return explanation

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
    explanation = None

    data = parse_json_object(response_text)
    if data and "differential" in data:
        try:
            ddx_res = DDxResult.model_validate(data)
            complete = True
        except Exception:
            ddx_res = None

    if ddx_res:
        explanation = await explain_in_plain_language(ddx_res)

    return ChatOutputPayload(
        message=response_text,
        complete=complete,
        ddx_result=ddx_res,
        explanation=explanation
    )

@app.post("/api/chat", response_model=AgentResponse)
@limiter.limit("10/minute")
def process_chat(request: Request, req: ChatRequest):
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

@app.get("/api/results")
def get_benchmark_results():
    """Benchmark results from eval/results/results.csv, summarised per arm (used by the mobile app)."""
    csv_path = os.path.join(os.path.dirname(__file__), "..", "eval", "results", "results.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="Benchmark results not found")

    with open(csv_path, "r", encoding="utf-8") as f:
        rows = [
            {"case_id": r["case_id"], "arm": r["arm"], "position": int(r["position"]), "turn_count": int(r["turn_count"])}
            for r in csv.DictReader(f)
        ]

    arms = []
    for arm in [a.value for a in PromptArm]:
        arm_rows = [r for r in rows if r["arm"] == arm]
        if not arm_rows:
            continue
        n = len(arm_rows)
        arms.append({
            "arm": arm,
            "cases": n,
            "top1": sum(r["position"] == 1 for r in arm_rows) / n,
            "top5": sum(1 <= r["position"] <= 5 for r in arm_rows) / n,
            "avg_turns": sum(r["turn_count"] for r in arm_rows) / n,
        })
    return {"arms": arms, "cases": rows}

@app.delete("/api/session/{session_id}")
def reset_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "reset", "session_id": session_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
