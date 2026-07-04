from src.state import AgentState
from src.agents.intent_agent import query_llm

def critic_agent_node(state: AgentState) -> dict:
    """Reviews the Analyst's draft response against logs collected by investigator nodes to check for unsupported claims."""
    print("\n--- [Critic Agent] Auditing Analyst Draft Response ---")
    
    logs = state.get("logs", [])
    user_query = state.get("user_query", "")
    draft_response = state.get("draft_response", "")
    
    if state.get("disable_critic", False):
        print("[Critic Agent] Critic verification disabled via state flag. Bypassing check.")
        return {
            "critic_feedback": "PASS",
            "logs": logs + ["[Critic Agent] Critic verification disabled. Bypassed check."]
        }

    
    system_prompt = (
        "You are the Critic Agent for PrivAgent.\n"
        "Verify the Analyst's draft response against the raw investigator logs.\n"
        "Check if:\n"
        "  - The draft makes claims not backed by the logs.\n"
        "  - The draft contains contradictions or errors relative to the logs.\n"
        "Note: The Analyst is instructed to ignore irrelevant fallback findings (like unconnected tickets/code files) that do not directly answer the User Request. Do not flag the omission of these irrelevant details as an issue.\n"
        "If there are any issues, detail them clearly so the Analyst can fix them.\n"
        "If the draft is 100% correct and fully supported by the logs, respond with exactly the word 'PASS' and nothing else."
    )
    
    # Filter logs to keep only investigator success outputs, reducing prompt size to prevent timeouts
    filtered_logs = []
    for l in logs:
        l_lower = l.lower()
        if "success" in l_lower and ("docs agent" in l_lower or "sql agent" in l_lower or "code agent" in l_lower or "ticket agent" in l_lower or "ticket_agent" in l_lower):
            # If the log is very large (e.g. holds full document/file contents), extract only relevant context snippets
            if len(l) > 600:
                print(f"[Critic Agent] Extracting matching snippets from large log of length {len(l)}...")
                stop_words = {"the", "a", "an", "of", "and", "in", "to", "for", "is", "on", "at", "by", "with", "this", "that", "these", "those", "about", "say"}
                query_words = [w.strip("?.!,\"()[]{}") for w in user_query.lower().split()]
                keywords = [w for w in query_words if len(w) > 2 and w not in stop_words]
                
                lines = l.replace("\\n", "\n").replace("\\r", "\n").split("\n")
                matching_lines = []
                for line in lines:
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in keywords) or any(kw in line_lower for kw in ["cgpa", "gpa", "roll", "nit", "warangal", "thakre", "yash"]):
                        matching_lines.append(line.strip())
                
                if matching_lines:
                    cropped_log = f"[Docs Agent SUCCESS (Filtered Snippets)]:\n" + "\n".join(matching_lines[:15])
                    filtered_logs.append(cropped_log)
                else:
                    cropped_log = f"[Docs Agent SUCCESS (Fallback Crop)]:\n" + "\n".join(lines[:10])
                    filtered_logs.append(cropped_log)
            else:
                filtered_logs.append(l)
    if not filtered_logs:
        filtered_logs = logs

    prompt = (
        f"User Request: {user_query}\n\n"
        f"Analyst Draft Response:\n{draft_response}\n\n"
        f"Investigator Logs:\n" + "\n".join([f"- {l}" for l in filtered_logs])
    )
    
    state_logs = {"logs": list(logs)}
    
    # 1. Bypass LLM for simple greetings to avoid CPU/model audit delays
    query_clean = user_query.strip().lower().rstrip("?.! ")
    greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "."]
    if query_clean in greetings:
        feedback = "PASS"
    else:
        feedback = query_llm(prompt, system_prompt, state_to_append_logs=state_logs)
        
    print(f"[Critic Agent] Audit Feedback: {feedback}")
    
    return {
        "critic_feedback": feedback,
        "logs": state_logs["logs"] + [f"[Critic Agent] Audited draft. Result: {feedback[:120]}..."]
    }
