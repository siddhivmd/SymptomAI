from typing import List
from models import AgentResponse, PromptArm, Message
from llm_client import LLMClient

VERBATIM_DISCLAIMER = "This is an educational demo, not a medical device. It does not provide medical advice. Consult a licensed clinician for any health concern."

SYSTEM_PROMPT = f"""You are a helpful AI health assistant. Answer the user's health questions conversationally.

IMPORTANT REQUIREMENT:
You must always include this disclaimer string verbatim in every response:
"{VERBATIM_DISCLAIMER}"
"""

# Alias for backward compatibility
BASE_SYSTEM_INSTRUCTION = SYSTEM_PROMPT

class BaseAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def run(self, history: List[Message], patient_age: int = 40, patient_gender: str = "Unspecified") -> AgentResponse:
        formatted_history = "\n".join([f"{m.role.upper()}: {m.content}" for m in history])
        prompt = f"""
Patient Demographics: Age {patient_age}, Gender: {patient_gender}

Conversation History:
{formatted_history}

Analyze the patient presentation using standard conversational baseline diagnostic reasoning. Generate your differential diagnosis, triage recommendation, and follow-up questions.
"""
        raw_json = self.llm_client.generate_json(
            prompt=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=AgentResponse,
            max_tokens=450
        )
        raw_json["inquiry_arm"] = PromptArm.BASE.value
        return AgentResponse(**raw_json)
