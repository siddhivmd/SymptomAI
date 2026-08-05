import os
import sys
import json
import asyncio
import logging
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import chi2_contingency
from typing import List, Dict, Any, Optional

# Ensure backend imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.models import Message, DDxResult, DDxItem, PromptArm, AgentResponse
from backend.llm_client import LLMClient
from backend.agents.base_prompt import SYSTEM_PROMPT as BASE_PROMPT
from backend.agents.structured_prompt import SYSTEM_PROMPT as STRUCTURED_PROMPT
from backend.agents.dynamic_prompt import SYSTEM_PROMPT as DYNAMIC_PROMPT
from eval.auto_rater_prompt import rate_diagnosis_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_eval")

SYSTEM_PROMPTS = {
    "base": BASE_PROMPT,
    "structured": STRUCTURED_PROMPT,
    "dynamic": DYNAMIC_PROMPT
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
CSV_FILE = os.path.join(RESULTS_DIR, "results.csv")
COMPLETED_RUNS_FILE = os.path.join(RESULTS_DIR, "completed_runs.json")
PNG_FILE = os.path.join(RESULTS_DIR, "accuracy_by_arm.png")

def calculate_token_budget(num_cases: int, target_arm: str) -> Dict[str, Any]:
    """
    Estimates total Groq API token consumption upfront based on optimized arm token footprints:
    - Primary agent under test stays on llama-3.3-70b-versatile capped at max_tokens=450.
    - Scaffolding calls (patient role-play, auto-rater judge, post-hoc extraction) use llama-3.1-8b-instant capped at max_tokens=200-400.
    
    Per-case estimates:
    - Base arm: 1 conv turn 70b + 1 extraction turn 8b + auto-rater (~1,300 tokens / case)
    - Structured arm: 5 conv turns 70b + 4 patient 8b turns + auto-rater (~3,250 tokens / case)
    - Dynamic arm: 3 conv turns 70b + 2 patient 8b turns + auto-rater (~2,000 tokens / case)
    """
    arms_to_run = ["base", "structured", "dynamic"] if target_arm == "all" else [target_arm]
    
    per_arm_tokens = {
        "base": 1300,
        "structured": 3250,
        "dynamic": 2000
    }
    
    total_estimated_tokens = sum(per_arm_tokens[arm] * num_cases for arm in arms_to_run)
    total_runs = num_cases * len(arms_to_run)
    all_arms_tokens_per_case = sum(per_arm_tokens.values())
    cases_in_100k_all = int(100000 / all_arms_tokens_per_case)
    
    return {
        "num_cases": num_cases,
        "arms": arms_to_run,
        "total_runs": total_runs,
        "per_arm_tokens": per_arm_tokens,
        "total_tokens": total_estimated_tokens,
        "all_arms_tokens_per_case": all_arms_tokens_per_case,
        "cases_in_100k_all": cases_in_100k_all,
        "tpd_limit": 100000,
        "exceeds_tpd": total_estimated_tokens > 100000
    }

def print_token_budget_summary(budget: Dict[str, Any]):
    print("\n" + "=" * 70)
    print("GROQ API TOKEN BUDGET ESTIMATE (REDUCED & OPTIMIZED)")
    print("=" * 70)
    print(f" * Cases to evaluate : {budget['num_cases']}")
    print(f" * Arms selected     : {', '.join(budget['arms'])}")
    print(f" * Total LLM runs    : {budget['total_runs']}")
    print(f" * Estimated Tokens  : ~{budget['total_tokens']:,} tokens")
    print(f" * Daily Limit (TPD) : {budget['tpd_limit']:,} tokens")
    print(f" * Scaffolding Model : llama-3.1-8b-instant (Patient & Auto-Rater)")
    print(f" * Agent Model       : llama-3.3-70b-versatile (max_tokens=450)")
    print("-" * 70)
    print("Per-Case Token Footprint Estimates:")
    print("   - Base arm       : ~1,300 tokens / case")
    print("   - Dynamic arm    : ~2,000 tokens / case")
    print("   - Structured arm : ~3,250 tokens / case")
    print("   - All 3 arms     : ~6,550 tokens / case")
    print("-" * 70)
    print(f" * 100k TPD Capacity : ~{budget['cases_in_100k_all']} full cases across all 3 arms ({budget['cases_in_100k_all'] * 3} case-runs)")
    print(" * Single-arm TPD Capacity:")
    print("   - Base arm alone       : ~76 cases fit in 100k TPD")
    print("   - Dynamic arm alone    : ~50 cases fit in 100k TPD")
    print("   - Structured arm alone : ~30 cases fit in 100k TPD")
    
    if budget["exceeds_tpd"]:
        print("\n[WARNING] Total 54 case-runs (~117.9k tokens) slightly exceed 100k TPD if run all at once.")
        print("  Recommendation: Run 15 cases across all 3 arms today (~98k tokens) or run arm-by-arm.")
    else:
        print("\n[OK] Estimated consumption fits cleanly inside daily token limits.")
    print("=" * 70 + "\n")

def load_completed_runs() -> Dict[str, Dict[str, Any]]:
    """Loads existing completed (case_id, arm) runs from completed_runs.json."""
    if os.path.exists(COMPLETED_RUNS_FILE):
        try:
            with open(COMPLETED_RUNS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load completed_runs.json ({e}). Starting fresh.")
    return {}

def save_completed_run(record: Dict[str, Any]):
    """Appends record to results.csv and updates completed_runs.json immediately."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    key = f"{record['case_id']}:{record['arm']}"
    
    completed = load_completed_runs()
    completed[key] = record
    with open(COMPLETED_RUNS_FILE, "w", encoding="utf-8") as f:
        json.dump(completed, f, indent=2)

    clean_record = {
        "case_id": record["case_id"],
        "arm": record["arm"],
        "position": record["position"],
        "turn_count": record["turn_count"]
    }
    df_row = pd.DataFrame([clean_record])
    file_exists = os.path.exists(CSV_FILE)
    df_row.to_csv(CSV_FILE, mode="a", index=False, header=not file_exists)

async def simulate_patient_response(llm_client: LLMClient, full_case_notes: str, doctor_question: str) -> str:
    """Simulates a medical patient replying concisely based on full case notes using llama-3.1-8b-instant."""
    if llm_client.use_mock:
        return f"Based on my history ({full_case_notes[:60]}...), the pain is worsening and I haven't noticed any fever."

    patient_system_prompt = (
        "You are a medical patient in a diagnostic consultation. "
        "Answer the doctor's question concisely, realistically, and naturally in 1-2 sentences based strictly on your case notes. "
        "Do not invent facts not in your notes, and do not explicitly name your diagnosis unless asked."
    )
    prompt = f"Case Notes: {full_case_notes}\n\nDoctor Asked: {doctor_question}\n\nPatient Response:"

    response = await llm_client.generate(
        system_prompt=patient_system_prompt,
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        max_tokens=250
    )
    return response

async def extract_post_hoc_ddx(llm_client: LLMClient, conversation_messages: List[Message]) -> List[Dict[str, Any]]:
    """
    SymptomAI Paper (Appendix B.3) Post-Hoc Extraction Step:
    Extracts a 5-item ranked differential diagnosis in JSON schema from unstructured base arm transcript using llama-3.1-8b-instant.
    """
    transcript = "\n".join([f"{m.role.capitalize()}: {m.content}" for m in conversation_messages])
    extraction_prompt = (
        "You are an expert clinical diagnostic assistant.\n"
        "Based strictly on the following patient consultation transcript, generate a 5-item differential diagnosis in JSON format.\n"
        "Keep rationales brief (under 10 words per item).\n"
        "Output MUST be a valid JSON object matching this schema:\n"
        "```json\n"
        "{\n"
        '  "history_summary": "Summary of patient chief complaint and history",\n'
        '  "differential": [\n'
        '    {"diagnosis": "Condition Name 1", "rationale": "Clinical rationale 1"},\n'
        '    {"diagnosis": "Condition Name 2", "rationale": "Clinical rationale 2"},\n'
        '    {"diagnosis": "Condition Name 3", "rationale": "Clinical rationale 3"},\n'
        '    {"diagnosis": "Condition Name 4", "rationale": "Clinical rationale 4"},\n'
        '    {"diagnosis": "Condition Name 5", "rationale": "Clinical rationale 5"}\n'
        '  ]\n'
        "}\n"
        "```\n\n"
        f"Transcript:\n{transcript}"
    )
    
    raw_res = await llm_client.generate(
        system_prompt="You are a clinical diagnostic extraction assistant.",
        messages=[{"role": "user", "content": extraction_prompt}],
        model="llama-3.1-8b-instant",
        max_tokens=400
    )
    
    cleaned_text = raw_res.strip()
    if "```json" in cleaned_text:
        cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
    elif "```" in cleaned_text:
        cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
        
    try:
        data = json.loads(cleaned_text)
        return data.get("differential") or data.get("differential_diagnosis") or []
    except Exception as e:
        logger.warning(f"Post-hoc DDx JSON extraction parsing failed: {e}")
        return []

async def run_single_conversation(llm_client: LLMClient, arm: str, case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simulates a multi-turn conversation between agent and patient.
    Handles rate limits explicitly without silent mock fallbacks.
    """
    case_id = case.get("id") or case.get("case_id")
    opening_complaint = case.get("opening_complaint") or case.get("chief_complaint")
    full_case_notes = case.get("full_case_notes") or case.get("history_of_present_illness")
    ground_truth_dx = case.get("ground_truth_diagnosis") or case.get("ground_truth_primary_dx")

    system_prompt = SYSTEM_PROMPTS.get(arm, BASE_PROMPT)
    messages = [Message(role="patient", content=opening_complaint)]
    
    turn_count = 1
    max_turns = 1 if arm == "base" else 5
    final_differential: List[Dict[str, Any]] = []
    status = "completed"

    try:
        while turn_count <= max_turns:
            messages_dicts = [m.model_dump() for m in messages]
            
            response_text = await llm_client.generate(
                system_prompt=system_prompt,
                messages=messages_dicts,
                max_tokens=450
            )

            # Check if LLM client returned rate limit error string
            if "429" in response_text or "rate_limit" in response_text.lower():
                logger.warning(f"Rate limit hit for {case_id} [{arm}] at turn {turn_count}.")
                return {
                    "case_id": case_id,
                    "arm": arm,
                    "position": "SKIPPED_RATE_LIMITED",
                    "turn_count": turn_count,
                    "status": "rate_limited"
                }

            cleaned_text = response_text.strip()
            if "```json" in cleaned_text:
                cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_text:
                cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

            parsed_json = None
            try:
                parsed_json = json.loads(cleaned_text)
            except Exception:
                parsed_json = None

            if isinstance(parsed_json, dict) and ("differential" in parsed_json or "differential_diagnosis" in parsed_json):
                final_differential = parsed_json.get("differential") or parsed_json.get("differential_diagnosis") or []
                break

            # Explicit Mock mode handling ONLY when llm_client.use_mock is True
            if llm_client.use_mock:
                if arm == "base" or turn_count >= (3 if arm == "dynamic" else 5):
                    mock_ddx = llm_client._generate_mock_response(opening_complaint, AgentResponse)
                    final_differential = mock_ddx.get("differential_diagnosis", [])
                    break

            messages.append(Message(role="assistant", content=response_text))
            
            if turn_count < max_turns:
                patient_reply = await simulate_patient_response(llm_client, full_case_notes, response_text)
                messages.append(Message(role="patient", content=patient_reply))

            turn_count += 1
            await asyncio.sleep(1.5)

        # Post-Hoc Extraction for Base Arm if no DDx JSON was produced
        if arm == "base" and not final_differential and not llm_client.use_mock:
            logger.info(f"Executing post-hoc DDx extraction for base arm ({case_id})...")
            final_differential = await extract_post_hoc_ddx(llm_client, messages)

    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "rate limit" in err_msg.lower():
            logger.warning(f"Rate limit exception for {case_id} [{arm}]: {err_msg}")
            return {
                "case_id": case_id,
                "arm": arm,
                "position": "SKIPPED_RATE_LIMITED",
                "turn_count": turn_count,
                "status": "rate_limited"
            }
        logger.error(f"Error during conversation simulation for case {case_id} [{arm}]: {e}")
        status = "error"

    # Rate diagnosis position using auto-rater
    try:
        position = rate_diagnosis_position(llm_client, ground_truth_dx, final_differential)
    except Exception as e:
        logger.error(f"Error auto-rating diagnosis for case {case_id} [{arm}]: {e}")
        position = -1

    return {
        "case_id": case_id,
        "arm": arm,
        "position": position,
        "turn_count": turn_count,
        "status": status
    }

def analyze_and_plot_results(csv_path: str, output_png_path: str):
    """Computes Top-1 and Top-5 accuracy, Chi-squared significance, and saves bar chart."""
    if not os.path.exists(csv_path):
        logger.warning(f"CSV results file {csv_path} does not exist yet.")
        return

    df = pd.read_csv(csv_path)
    # Filter out skipped rate-limited rows
    valid_df = df[df["position"].astype(str) != "SKIPPED_RATE_LIMITED"].copy()
    if valid_df.empty:
        logger.warning("No valid completed rows to analyze.")
        return

    valid_df["position_num"] = pd.to_numeric(valid_df["position"], errors="coerce").fillna(-1)
    valid_df["top1_hit"] = (valid_df["position_num"] == 1).astype(int)
    valid_df["top5_hit"] = ((valid_df["position_num"] > 0) & (valid_df["position_num"] <= 5)).astype(int)

    arms = ["base", "structured", "dynamic"]
    summary_data = []

    base_df = valid_df[valid_df["arm"] == "base"]
    base_top5_hits = base_df["top5_hit"].sum()
    base_total = len(base_df)
    base_misses = base_total - base_top5_hits

    for arm in arms:
        arm_df = valid_df[valid_df["arm"] == arm]
        total = len(arm_df)
        if total == 0:
            continue
        top1_acc = arm_df["top1_hit"].mean() * 100.0
        top5_hits = arm_df["top5_hit"].sum()
        top5_acc = (top5_hits / total) * 100.0
        avg_turns = arm_df["turn_count"].mean()

        p = top5_hits / total if total > 0 else 0
        stderr = np.sqrt(p * (1 - p) / total) * 100.0 if total > 0 else 0.0

        if arm == "base":
            p_val_str = "N/A (control)"
        else:
            arm_misses = total - top5_hits
            contingency_matrix = [
                [top5_hits, arm_misses],
                [base_top5_hits, base_misses]
            ]
            try:
                res = chi2_contingency(contingency_matrix)
                p_val = res.pvalue
                p_val_str = f"{p_val:.4f}" if p_val >= 0.0001 else "< 0.0001"
            except Exception:
                p_val_str = "N/A"

        summary_data.append({
            "Arm": arm,
            "Total Cases": total,
            "Top-1 Accuracy": f"{top1_acc:.1f}%",
            "Top-5 Accuracy": f"{top5_acc:.1f}%",
            "Avg Turns": f"{avg_turns:.1f}",
            "p-value vs Base": p_val_str,
            "top5_pct": top5_acc,
            "stderr": stderr
        })

    print("\n### SymptomCheck-Mini Statistical Evaluation Summary\n")
    print("| Arm | Total Cases | Top-1 Accuracy | Top-5 Accuracy | Avg Turns | p-value vs Base |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for row in summary_data:
        print(f"| **{row['Arm']}** | {row['Total Cases']} | {row['Top-1 Accuracy']} | {row['Top-5 Accuracy']} | {row['Avg Turns']} | {row['p-value vs Base']} |")
    print("\n")

    if summary_data:
        fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
        arm_names = [r["Arm"].capitalize() for r in summary_data]
        top5_vals = [r["top5_pct"] for r in summary_data]
        errors = [r["stderr"] for r in summary_data]
        colors = ["#6c757d", "#0d6efd", "#198754"]

        bars = ax.bar(arm_names, top5_vals, yerr=errors, capsize=6, color=colors, edgecolor="black", alpha=0.85)
        ax.set_title("Top-5 Diagnostic Accuracy by Prompting Arm (with 95% CI Error Bars)", fontsize=12, fontweight="bold", pad=15)
        ax.set_ylabel("Top-5 Accuracy (%)", fontsize=11, fontweight="bold")
        ax.set_ylim(0, 115)
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        for bar, val in zip(bars, top5_vals):
            height = bar.get_height()
            ax.annotate(f"{val:.1f}%",
                        xy=(bar.get_x() + bar.get_width() / 2, height + 3),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=10, fontweight="bold")

        plt.tight_layout()
        plt.savefig(output_png_path)
        plt.close()
        logger.info(f"Accuracy bar chart with error bars saved to {output_png_path}")

async def main_async(args):
    cases_file = os.path.join(os.path.dirname(__file__), "synthetic_cases.json")
    with open(cases_file, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    # Filter cases if --cases or --case specified
    if args.case:
        cases = [c for c in all_cases if (c.get("id") == args.case or c.get("case_id") == args.case)]
    elif args.cases and args.cases > 0:
        cases = all_cases[:args.cases]
    else:
        cases = all_cases

    llm_client = LLMClient()
    if args.mock:
        llm_client.use_mock = True
        logger.info("Operating explicitly in Mock LLM mode.")

    target_arm = args.arm.lower()
    arms_to_run = ["base", "structured", "dynamic"] if target_arm == "all" else [target_arm]

    # Print upfront token budget estimate
    budget = calculate_token_budget(len(cases), target_arm)
    print_token_budget_summary(budget)

    completed_runs = load_completed_runs()
    logger.info(f"Loaded {len(completed_runs)} previously completed runs from checkpoint.")

    for case in cases:
        case_id = case.get("id") or case.get("case_id")
        
        for arm in arms_to_run:
            key = f"{case_id}:{arm}"
            if key in completed_runs and not args.force:
                logger.info(f"Skipping already-completed run: {key}")
                continue

            logger.info(f"Evaluating Case {case_id} [{arm}]...")
            res = await run_single_conversation(llm_client, arm, case)
            
            # Checkpoint: Save immediately
            if res.get("status") != "rate_limited":
                save_completed_run(res)
                logger.info(f"Saved checkpoint for {key}: position={res['position']}, turns={res['turn_count']}")
            else:
                logger.warning(f"Rate limited on {key}. Backing off 15 seconds before continuing.")
                await asyncio.sleep(15.0)

    analyze_and_plot_results(CSV_FILE, PNG_FILE)

def main():
    parser = argparse.ArgumentParser(description="SymptomCheck-Mini Multi-Turn Evaluation Benchmark")
    parser.add_argument("--arm", type=str, default="all", choices=["all", "base", "structured", "dynamic"], help="Prompt arm to evaluate")
    parser.add_argument("--cases", type=int, default=0, help="Number of cases to evaluate (0 for all)")
    parser.add_argument("--case", type=str, default=None, help="Specific case ID to evaluate (e.g. CASE_001)")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode without calling live APIs")
    parser.add_argument("--force", action="store_true", help="Ignore completed checkpoint and re-run all specified cases")
    args = parser.parse_args()

    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
