from src.state import AgentState

def human_approval_node(state: AgentState) -> dict:
    """Human-in-the-Loop approval gate node. Excutes when resumed with approval payload."""
    print("\n--- [Human Approval] Manual Review Gate ---")
    logs = state.get("logs", [])
    approved = state.get("approved", False)
    
    if not approved:
        print("[Human Approval] Security Audit Warning: Approval flag is False.")
        return {"errors": state.get("errors", []) + ["Human Approval check failed or rejected."]}
        
    print("[Human Approval] Approval confirmed. Proceeding to execution node...")
    return {
        "logs": logs + ["[Human Approval] Action manually authorized by Administrator."]
    }
