from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum

class TriageLevel(str, Enum):
    EMERGENCY = "Emergency"
    URGENT = "Urgent"
    ROUTINE = "Routine"
    SELF_CARE = "Self-care"

class PromptArm(str, Enum):
    BASE = "base"
    STRUCTURED = "structured"
    DYNAMIC = "dynamic"

class Message(BaseModel):
    role: str = Field(description="Role in conversation: patient, assistant, or system")
    content: str = Field(description="Message content")

# Alias for backward compatibility
ChatMessage = Message

class DDxItem(BaseModel):
    diagnosis: str = Field(default="", description="Medical condition or diagnosis name")
    rationale: str = Field(default="", description="Clinical rationale for this potential diagnosis")
    condition_name: Optional[str] = None
    icd10_code: Optional[str] = None
    confidence_score: float = Field(default=0.5, description="Estimated confidence score between 0.0 and 1.0")
    key_supporting_symptoms: List[str] = Field(default_factory=list)
    recommended_urgency: TriageLevel = Field(default=TriageLevel.ROUTINE)

    def model_post_init(self, __context):
        if not self.diagnosis and self.condition_name:
            self.diagnosis = self.condition_name
        elif not self.condition_name and self.diagnosis:
            self.condition_name = self.diagnosis
        if not self.rationale:
            if self.key_supporting_symptoms:
                self.rationale = "Supporting symptoms: " + ", ".join(self.key_supporting_symptoms)
            else:
                self.rationale = "Clinical correlation suggested."


class DDxResult(BaseModel):
    history_summary: str = Field(description="Summary of clinical history collected")
    differential: List[DDxItem] = Field(default_factory=list, description="List of differential diagnoses")
    disclaimer: str = Field(
        default="For educational and benchmark research purposes only. Not a medical device.",
        description="Medical disclaimer"
    )

class AgentResponse(BaseModel):
    followup_questions: List[str] = Field(default_factory=list)
    differential_diagnosis: List[DDxItem] = Field(default_factory=list)
    triage_level: TriageLevel = Field(default=TriageLevel.ROUTINE)
    clinical_rationale: str = ""
    inquiry_arm: PromptArm = Field(default=PromptArm.BASE)

class Conversation(BaseModel):
    arm: Literal["base", "structured", "dynamic"] = "base"
    messages: List[Message] = Field(default_factory=list)
    turn_count: int = 0
    session_id: Optional[str] = None
    prompt_arm: Optional[PromptArm] = PromptArm.BASE
    patient_age: Optional[int] = 40
    patient_gender: Optional[str] = "Unspecified"


class ClinicalCase(BaseModel):
    id: Optional[str] = None
    case_id: Optional[str] = None
    opening_complaint: str = ""
    chief_complaint: str = ""
    patient_age: int = 30
    patient_gender: str = "Unspecified"
    full_case_notes: str = ""
    history_of_present_illness: str = ""
    ground_truth_diagnosis: str = ""
    ground_truth_primary_dx: str = ""
    ground_truth_top_differentials: List[str] = Field(default_factory=list)
    expected_triage_level: TriageLevel = Field(default=TriageLevel.ROUTINE)
    red_flags: List[str] = Field(default_factory=list)

    def model_post_init(self, __context):
        if not self.case_id and self.id:
            self.case_id = self.id
        elif not self.id and self.case_id:
            self.id = self.case_id
        if not self.chief_complaint and self.opening_complaint:
            self.chief_complaint = self.opening_complaint
        elif not self.opening_complaint and self.chief_complaint:
            self.opening_complaint = self.chief_complaint
        if not self.history_of_present_illness and self.full_case_notes:
            self.history_of_present_illness = self.full_case_notes
        elif not self.full_case_notes and self.history_of_present_illness:
            self.full_case_notes = self.history_of_present_illness
        if not self.ground_truth_primary_dx and self.ground_truth_diagnosis:
            self.ground_truth_primary_dx = self.ground_truth_diagnosis
        elif not self.ground_truth_diagnosis and self.ground_truth_primary_dx:
            self.ground_truth_diagnosis = self.ground_truth_primary_dx


class EvalResult(BaseModel):
    case_id: str
    arm: PromptArm
    top1_match: bool
    top3_match: bool
    triage_accuracy: bool
    inquiry_quality_score: float = Field(description="Score from 0 to 100 for question appropriateness")
    safety_score: float = Field(description="Score from 0 to 100 for identifying red flags and safe triage")
    auto_rater_explanation: str

class EvalSummary(BaseModel):
    arm: PromptArm
    total_cases: int
    top1_accuracy: float
    top3_accuracy: float
    triage_accuracy: float
    avg_inquiry_quality: float
    avg_safety_score: float
