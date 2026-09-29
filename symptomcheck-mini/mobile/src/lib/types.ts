// Mirrors the FastAPI models in backend/models.py and backend/main.py.

export type Arm = "base" | "structured" | "dynamic";
export type ArmChoice = Arm | "random";

export interface ChatMessage {
  role: "patient" | "assistant";
  content: string;
}

export interface DDxItem {
  diagnosis: string;
  rationale: string;
  condition_name?: string | null;
}

export interface DDxResult {
  history_summary: string;
  differential: DDxItem[];
  disclaimer: string;
}

export interface PlainExplanation {
  summary: string;
  items: { plain_name: string; explanation: string }[];
  next_steps: string;
}

export interface ChatResponse {
  message: string;
  complete: boolean;
  ddx_result: DDxResult | null;
  explanation?: PlainExplanation | null;
}

export interface HealthResponse {
  status: string;
  mock_mode: boolean;
}

export interface ArmSummary {
  arm: Arm;
  cases: number;
  top1: number;
  top5: number;
  avg_turns: number;
}

export interface CaseResult {
  case_id: string;
  arm: Arm;
  position: number;
  turn_count: number;
}

export interface ResultsResponse {
  arms: ArmSummary[];
  cases: CaseResult[];
}
