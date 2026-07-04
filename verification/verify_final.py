import time
from verification.verify_phase3 import run_phase3_test
from verification.verify_phase4 import run_phase4_test
from verification.verify_phase5 import run_pii_and_rbac_tests, run_hitl_test
from verification.verify_phase6 import test_api_endpoints

def run_all_validation_checks():
    print("\n" + "#"*80)
    print("                PRIVAGENT INTEGRATED END-TO-END VALIDATION SUITE")
    print("#"*80)
    
    # 1. Phase 3: Investigator actual tools & fallbacks
    print("\n[Suite 1/5] Executing Phase 3 Investigator Capabilities...")
    run_phase3_test()
    time.sleep(2)
    
    # 2. Phase 4: Critic & Debate QA synthesis
    print("\n[Suite 2/5] Executing Phase 4 Debate & Reconciled Synthesis...")
    run_phase4_test()
    time.sleep(2)
    
    # 3. Phase 5: Security sanitization and guest RBAC
    print("\n[Suite 3/5] Executing Phase 5 Security and RBAC Guardrails...")
    run_pii_and_rbac_tests()
    time.sleep(2)
    
    # 4. Phase 5: Human-in-the-Loop approval interrupts
    print("\n[Suite 4/5] Executing Phase 5 Human-in-the-Loop (HITL) Gate...")
    run_hitl_test()
    time.sleep(2)
    
    # 5. Phase 6: REST API Endpoint Integrations
    print("\n[Suite 5/5] Executing Phase 6 FastAPI endpoints & Telemetry logs...")
    test_api_endpoints()
    
    print("\n" + "#"*80)
    print("                 ALL PRIVAGENT VALIDATION CHECKS COMPLETED SUCCESSFULLY!")
    print("#"*80 + "\n")

if __name__ == "__main__":
    run_all_validation_checks()
