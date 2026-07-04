import urllib.request
import json
import time

def test_api_polling():
    print("=== [API Polling Verification Test] ===")
    
    # 1. Trigger query
    payload = {
        "query": "hello what is langgraph",
        "role": "admin",
        "model": "qwen3:0.6b" # Use small model for fast test
    }
    
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/query",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            print(f"Query Trigger response: {res_data}")
            thread_id = res_data.get("thread_id")
            assert res_data.get("status") == "running", "Query should start in running state"
            assert thread_id is not None, "Thread ID must be returned"
    except Exception as e:
        print(f"Failed to trigger query: {e}")
        return False

    # 2. Poll status until completion
    print(f"Polling status for thread: {thread_id}...")
    for _ in range(90): # up to 180 seconds
        time.sleep(2)
        status_req = urllib.request.Request(f"http://127.0.0.1:8000/api/status/{thread_id}")
        try:
            with urllib.request.urlopen(status_req, timeout=5) as response:
                status_data = json.loads(response.read().decode("utf-8"))
                status = status_data.get("status")
                logs = status_data.get("logs", [])
                print(f"Poll check - Status: {status} | Logs count: {len(logs)}")
                
                if status == "completed":
                    print("SUCCESS: Graph execution completed!")
                    print(f"Final Response snippet: {status_data.get('final_response', '')[:200]}...")
                    return True
                elif status == "interrupted":
                    print("SUCCESS: Graph execution interrupted (HITL authorization required)!")
                    return True
        except Exception as e:
            print(f"Polling query failed: {e}")
            return False

    print("FAILED: Polling timed out after 60 seconds.")
    return False

if __name__ == "__main__":
    test_api_polling()
