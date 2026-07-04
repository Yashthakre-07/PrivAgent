import re
from src.state import AgentState

def security_agent_node(state: AgentState) -> dict:
    """Audits the input query for security concerns, PII redactions, and RBAC policies."""
    print("\n--- [Security Agent] Auditing Request Security & PII ---")
    
    query = state.get("user_query", "")
    role = state.get("user_role", "guest")  # Default to guest for security
    logs = state.get("logs", [])
    
    # 1. PII Redaction (Email & Phone Numbers)
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    phone_pattern = r"\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b"
    
    redacted_query = re.sub(email_pattern, "[EMAIL_REDACTED]", query)
    redacted_query = re.sub(phone_pattern, "[PHONE_REDACTED]", redacted_query)
    
    if redacted_query != query:
        print(f"[Security Agent] PII detected and redacted: '{redacted_query}'")
        logs.append(f"[Security Agent] Redacted PII from user query.")
        
    # 2. RBAC Policy Check
    # Modifying keywords that require admin authorization
    write_keywords = ["update", "delete", "drop", "create", "insert", "modify", "recreate"]
    query_words = redacted_query.lower().split()
    
    requires_write = any(kw in query_words for kw in write_keywords)
    
    if requires_write and role != "admin":
        print(f"[Security Agent] RBAC VIOLATION: Role '{role}' cannot request write operations.")
        return {
            "user_query": redacted_query,
            "final_response": "SECURITY BLOCK: Unauthorized write operation requested for guest role.",
            "logs": logs + ["[Security Agent SUCCESS] Blocked guest write request."]
        }
        
    print("[Security Agent] Request audited successfully.")
    return {
        "user_query": redacted_query,
        "logs": logs + ["[Security Agent SUCCESS] Request verified and sanitized."]
    }
