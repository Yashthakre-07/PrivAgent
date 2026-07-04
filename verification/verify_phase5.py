from src.graph import get_graph

def run_pii_and_rbac_tests():
    print("\n" + "="*80)
    print("RUNNING PHASE 5 SECURITY & RBAC AUDIT TESTS")
    print("="*80)
    
    graph = get_graph()
    
    # --- TEST 1: PII Masking ---
    print("\n--- [Test 1] PII Redaction Audit ---")
    query_with_pii = (
        "Hello, my email is developer_admin@privagent.io and my phone is +1-555-019-2834. "
        "Please scan our code repository files for database configurations."
    )
    # Guest user role (guest should be allowed to run code scans, which are read-only)
    config = {"configurable": {"thread_id": "pii_masking_thread"}}
    inputs = {"user_query": query_with_pii, "user_role": "guest", "approved": False}
    
    result = graph.invoke(inputs, config=config)
    
    # Look at the logs to confirm PII was redacted
    print(f"User Query after sanitization: '{result.get('user_query')}'")
    print(f"Resulting Final response: {result.get('final_response', '')[:200]}")
    
    # --- TEST 2: RBAC Block ---
    print("\n--- [Test 2] RBAC Unauthorized Write Blocking ---")
    write_query = "Please delete Initech customer records from the database."
    config = {"configurable": {"thread_id": "rbac_blocking_thread"}}
    inputs = {"user_query": write_query, "user_role": "guest", "approved": False}
    
    result = graph.invoke(inputs, config=config)
    print(f"Resulting Final Response: '{result.get('final_response')}'")
    print("============================================\n")

def run_hitl_test():
    print("\n" + "="*80)
    print("RUNNING PHASE 5 HUMAN-IN-THE-LOOP (HITL) GATE TEST")
    print("="*80)
    
    graph = get_graph()
    config = {"configurable": {"thread_id": "hitl_test_thread"}}
    
    # Admin role is allowed to trigger write actions, but must pass the HITL approval gate
    write_query = "Please update customer revenue loss for AcmeCorp to 60000.00."
    inputs = {"user_query": write_query, "user_role": "admin", "approved": False}
    
    # 1. Start execution. It should halt before human_approval node.
    print("\n[Step 1] Initializing write request. Expecting graph interrupt...")
    result = graph.invoke(inputs, config=config)
    
    state = graph.get_state(config)
    print(f"Current State Next Nodes to run: {state.next}")
    
    if "human_approval" in state.next:
        print("[Step 2] Graph halted successfully right before 'human_approval'!")
        
        # 2. Simulate manual approval from admin
        print("\n[Step 3] Simulating Administrator approval payload (approved=True)...")
        # Update thread state to set approved = True
        graph.update_state(config, {"approved": True}, as_node="human_approval")
        
        # 3. Resume graph execution by invoking with None input in a loop
        print("\n[Step 4] Resuming graph execution...")
        final_result = graph.invoke(None, config=config)
        
        # Loop to handle any subsequent interrupts for consecutive write tasks
        while True:
            state = graph.get_state(config)
            if "human_approval" in state.next:
                print("\n[HITL Gate] Interrupted again on subsequent write task! Approving...")
                graph.update_state(config, {"approved": True}, as_node="human_approval")
                final_result = graph.invoke(None, config=config)
            else:
                break
                
        print("\n--- FINAL RESUMED WORKFLOW RESPONSE ---")
        print(final_result.get("final_response", "No final response."))
        print("="*80 + "\n")
    else:
        print("[ERROR] Graph did not halt at human_approval gate!")
        print("="*80 + "\n")

if __name__ == "__main__":
    run_pii_and_rbac_tests()
    run_hitl_test()
