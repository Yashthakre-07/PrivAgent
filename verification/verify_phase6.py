import urllib.request
import json
import time

API_URL = "http://127.0.0.1:8000/api"

def make_request(endpoint: str, payload: dict) -> dict:
    url = f"{API_URL}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(f"[API Client Error] Request failed: {e}")
        return {}

def test_api_endpoints():
    print("\n" + "="*80)
    print("RUNNING PHASE 6 API INTEGRATION & VERIFICATION TESTS")
    print("="*80)
    
    # Wait 2 seconds to make sure server is fully loaded
    time.sleep(2)
    
    # --- TEST 1: PII Masking & Execution ---
    print("\n--- [API Test 1] PII Redaction Audit ---")
    query_pii = "My email is test_engineer@privagent.io. Scan code files for configurations."
    payload = {"query": query_pii, "role": "admin"}
    
    res = make_request("query", payload)
    print(f"Status: {res.get('status')}")
    print(f"Thread ID: {res.get('thread_id')}")
    print(f"Final response excerpt: {res.get('final_response', '')[:150]}")
    
    # --- TEST 2: RBAC Block ---
    print("\n--- [API Test 2] RBAC Unauthorized Write Blocking ---")
    query_write = "Delete Globex customer records from database."
    payload = {"query": query_write, "role": "guest"}
    
    res = make_request("query", payload)
    print(f"Status: {res.get('status')}")
    print(f"Final response: '{res.get('final_response')}'")
    
    # --- TEST 3: HITL Interruption & Approve Loop ---
    print("\n--- [API Test 3] Admin Write with HITL Approvals ---")
    query_hitl = "Update customer revenue loss for AcmeCorp to 60000.00."
    payload = {"query": query_hitl, "role": "admin"}
    
    res = make_request("query", payload)
    print(f"Initial Status: {res.get('status')}")
    print(f"Thread ID: {res.get('thread_id')}")
    
    if res.get("status") == "interrupted":
        print(f"Halted on node: '{res.get('next_node')}' for task: '{res.get('task_desc')}'")
        
        # Approve the task
        thread_id = res.get("thread_id")
        approve_payload = {"thread_id": thread_id, "approved": True}
        
        print("\nSending approve payload to resume...")
        approve_res = make_request("approve", approve_payload)
        
        # Resume loop if subsequent interrupts occur
        while approve_res.get("status") == "interrupted":
            print(f"Halted again on: '{approve_res.get('next_node')}' for task: '{approve_res.get('task_desc')}'")
            print("Approving subsequent interrupt...")
            approve_res = make_request("approve", {"thread_id": thread_id, "approved": True})
            
        print(f"Final Resumed Status: {approve_res.get('status')}")
        print("Final Synthesis Excerpt:")
        print(approve_res.get("final_response", "")[:300])
        print("="*80 + "\n")
        
if __name__ == "__main__":
    test_api_endpoints()
