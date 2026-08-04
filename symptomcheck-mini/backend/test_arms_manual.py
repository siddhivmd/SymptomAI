import os
import sys
import json
import asyncio
import urllib.request

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

from agents.base_prompt import SYSTEM_PROMPT as BASE_PROMPT
from agents.structured_prompt import SYSTEM_PROMPT as STRUCTURED_PROMPT
from agents.dynamic_prompt import SYSTEM_PROMPT as DYNAMIC_PROMPT

SYSTEM_PROMPTS = {
    "base": BASE_PROMPT,
    "structured": STRUCTURED_PROMPT,
    "dynamic": DYNAMIC_PROMPT
}

def test_arms():
    url = "http://127.0.0.1:8000/chat"
    message = "I have a headache"
    arms = ["base", "structured", "dynamic"]

    print("==========================================================================")
    print(f"TESTING ARMS WITH OPENING MESSAGE: '{message}'")
    print("==========================================================================\n")

    for arm in arms:
        print(f"--------------------------------------------------------------------------")
        print(f"ARM: {arm.upper()}")
        print(f"--------------------------------------------------------------------------")
        print(f"System Prompt preview:\n{SYSTEM_PROMPTS[arm][:200]}...\n")

        payload = {
            "arm": arm,
            "messages": [
                {"role": "patient", "content": message}
            ]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                print("MODEL FIRST RESPONSE:")
                print(res_data["message"])
                print(f"\n[Complete Flag]: {res_data['complete']}")
                print(f"[DDx Result Returned]: {res_data['ddx_result'] is not None}")
                print("--------------------------------------------------------------------------\n")
        except Exception as e:
            print(f"ERROR calling {arm}: {e}\n")

if __name__ == "__main__":
    test_arms()
