from typing import List
from models import AgentResponse, PromptArm, Message
from llm_client import LLMClient

VERBATIM_DISCLAIMER = "This is an educational demo, not a medical device. It does not provide medical advice. Consult a licensed clinician for any health concern."

SYSTEM_PROMPT = f"""You are an AI clinical symptom checker operating under a structured clinical inquiry protocol.

INSTRUCTIONS:
1. Ask a fixed sequence of history-of-present-illness questions covering:
   - Pain/symptom location
   - Onset
   - Severity on a scale of 0 to 10
   - Symptom quality (e.g. sharp, burning, dull, pressure)
   - Timing and frequency (constant or intermittent)
   - Aggravating and relieving factors
   - Associated symptoms
   - Medical risk factors and past medical history

2. Conduct this interview over at most 6 conversation turns.

3. Once history taking is complete (or after at most 6 turns), output a 5-item ranked differential diagnosis in JSON format using the exact schema:
{{
  "history_summary": "<concise summary of collected history>",
  "differential": [
    {{"diagnosis": "<Primary Condition>", "rationale": "<Clinical rationale supporting diagnosis>"}},
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
STRUCTURED_SYSTEM_INSTRUCTION = SYSTEM_PROMPT

class StructuredAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def run(self, history: List[Message], patient_age: int = 40, patient_gender: str = "Unspecified") -> AgentResponse:
        formatted_history = "\n".join([f"{m.role.upper()}: {m.content}" for m in history])
        prompt = f"""
Patient Profile: Age {patient_age}, Gender: {patient_gender}

Clinical Interview History:
{formatted_history}

Perform a structured clinical inquiry evaluation following the OPQRST and organ system review protocols. Construct a 5-item differential diagnosis.
"""
        raw_json = self.llm_client.generate_json(
            prompt=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=AgentResponse
        )
        raw_json["inquiry_arm"] = PromptArm.STRUCTURED.value
        return AgentResponse(**raw_json)
