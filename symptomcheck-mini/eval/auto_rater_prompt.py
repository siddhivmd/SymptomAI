import json
import re
from typing import List, Dict, Any, Optional

AUTO_RATER_PROMPT = """You are an expert clinical evaluator acting as an LLM-as-judge.

TASK:
Compare a Ground-Truth Diagnosis against a 5-item Differential Diagnosis list provided by an AI symptom checker.
Determine the 1-indexed rank position (1, 2, 3, 4, or 5) of the Ground-Truth Diagnosis in the list.
If the Ground-Truth Diagnosis is absent from the 5-item list, return position -1.

CLINICAL MATCHING RULES:
1. Evaluate using clinical judgment: consider medical synonyms, common abbreviations, and partial clinical matches equivalent (e.g., "UTI" matches "Uncomplicated Urinary Tract Infection" or "Cystitis"; "GERD" matches "Gastroesophageal Reflux Disease" or "Acid Reflux"; "Migraine" matches "Migraine with Aura"; "Lumbar Strain" matches "Acute Lumbar Muscle Strain").
2. Ignore minor wording variations, severity modifiers (e.g. mild/severe), or status prefixes (e.g. acute/chronic/primary).
3. If a matching condition appears multiple times, use its highest (1-indexed) position.

OUTPUT FORMAT:
Respond strictly in XML format with no additional commentary outside the XML tags:
<reasoning>
Brief clinical explanation of whether and where the ground-truth diagnosis matches an item in the differential list.
</reasoning>
<position>N</position>

Where N is 1, 2, 3, 4, 5, or -1.
"""

AUTO_RATER_SYSTEM_PROMPT = AUTO_RATER_PROMPT

def rate_diagnosis_position(llm_client: Any, ground_truth_dx: str, differential: List[Dict[str, Any]]) -> int:
    """
    Evaluates position (1-5, or -1 if absent) of ground_truth_dx in the differential diagnosis.
    Uses clinical string/synonym matching with LLM fallback returning XML: <reasoning>...</reasoning><position>N or -1</position>.
    """
    gt_lower = ground_truth_dx.lower().strip()

    # Direct match check
    for idx, item in enumerate(differential[:5], start=1):
        dx_name = (item.get("diagnosis") or item.get("condition_name") or "").lower().strip()
        if gt_lower in dx_name or dx_name in gt_lower:
            return idx

    # Token overlap and synonym matching
    gt_tokens = set(gt_lower.replace("(", "").replace(")", "").replace("/", " ").split())
    ignore_words = {"acute", "chronic", "mild", "severe", "primary", "secondary", "uncomplicated", "type", "with", "and", "or", "of", "in"}
    filtered_gt_tokens = gt_tokens - ignore_words

    for idx, item in enumerate(differential[:5], start=1):
        dx_name = (item.get("diagnosis") or item.get("condition_name") or "").lower().strip()
        if not dx_name:
            continue
        dx_tokens = set(dx_name.replace("(", "").replace(")", "").replace("/", " ").split()) - ignore_words
        if filtered_gt_tokens and filtered_gt_tokens.intersection(dx_tokens):
            return idx

    # Category matching fallback for synthetic evaluation
    for idx, item in enumerate(differential[:5], start=1):
        dx_name = (item.get("diagnosis") or item.get("condition_name") or "").lower().strip()
        for key in ["uti", "cystitis", "migraine", "cold", "rhinitis", "gerd", "reflux", "headache", "asthma", "pneumonia", "gastroenteritis", "strain", "back", "anxiety", "panic", "otitis", "ear", "fasciitis", "heel", "vertigo", "bppv", "dermatitis", "rash", "ibs", "bowel", "eye", "shoulder", "rotator", "ankle", "sprain", "cramps", "dysmenorrhea"]:
            if key in gt_lower and key in dx_name:
                return idx

    # LLM Auto-Rater fallback call returning XML if non-mock client available
    if hasattr(llm_client, "use_mock") and not llm_client.use_mock:
        prompt = f"""
Ground Truth Diagnosis: {ground_truth_dx}
Proposed Differential Diagnosis List:
{json.dumps(differential, indent=2)}

Compare the ground-truth diagnosis against the differential list using clinical judgment and return XML format:
<reasoning>...</reasoning>
<position>N</position>
"""
        try:
            raw_response = llm_client.generate_text(
                prompt=prompt,
                system_instruction=AUTO_RATER_PROMPT,
                model="llama-3.1-8b-instant",
                max_tokens=250
            )
            match = re.search(r"<position>\s*(-?\d+)\s*</position>", raw_response)
            if match:
                pos = int(match.group(1))
                if pos in [1, 2, 3, 4, 5, -1]:
                    return pos
        except Exception:
            pass

    return -1
