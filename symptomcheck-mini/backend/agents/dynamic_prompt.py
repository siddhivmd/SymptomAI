from typing import List
from models import AgentResponse, PromptArm, Message
from llm_client import LLMClient

VERBATIM_DISCLAIMER = "This is an educational demo, not a medical device. It does not provide medical advice. Consult a licensed clinician for any health concern."

SYSTEM_PROMPT = f"""You are an AI clinical symptom checker operating under an adaptive dynamic inquiry protocol.

INSTRUCTIONS:
1. You have full agency over which follow-up questions to ask based on patient responses to differentiate potential diagnoses.
2. You MUST ask at least 3 follow-up questions before you are allowed to output your final differential diagnosis.
3. After asking at least 3 clarifying questions, output a 5-item ranked differential diagnosis in JSON format matching this exact schema:
{{
  "history_summary": "<concise summary of patient symptoms and history>",
  "differential": [
    {{"diagnosis": "<Primary Diagnosis>", "rationale": "<Clinical rationale supporting diagnosis>"}},
    {{"diagnosis": "<Differential 2>", "rationale": "<Clinical rationale>"}},
    {{"diagnosis": "<Differential 3>", "rationale": "<Clinical rationale>"}},
    {{"diagnosis": "<Differential 4>", "rationale": "<Clinical rationale>"}},
    {{"diagnosis": "<Differential 5>", "rationale": "<Clinical rationale>"}}
  ],
  "disclaimer": "{VERBATIM_DISCLAIMER}"
}}

IMPORTANT REQUIREMENT:
You must always include this disclaimer string verbatim in your output:
"{VERBATIM_DISCLAIMER}"
"""

# Alias for backward compatibility
DYNAMIC_SYSTEM_INSTRUCTION = SYSTEM_PROMPT

class DynamicAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def run(self, history: List[Message], patient_age: int = 40, patient_gender: str = "Unspecified") -> AgentResponse:
        formatted_history = "\n".join([f"{m.role.upper()}: {m.content}" for m in history])
        prompt = f"""
Patient Profile: Age {patient_age}, Gender: {patient_gender}

Interview Trajectory:
{formatted_history}

Analyze differential diagnosis uncertainty and formulate adaptive follow-up questions or final 5-item differential diagnosis.
"""
        raw_json = self.llm_client.generate_json(
            prompt=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=AgentResponse
        )
        raw_json["inquiry_arm"] = PromptArm.DYNAMIC.value
        return AgentResponse(**raw_json)
