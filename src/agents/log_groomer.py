import json
from src.state import AgentState
from src.agents.intent_agent import query_llm

def log_groomer_node(state: AgentState) -> dict:
    """Background node to summarize raw agent results in logs, keeping context window clean."""
    print("\n--- [Log Groomer] Summarizing and compressing raw logs ---")
    logs = state.get("logs", [])
    if not logs:
        return {}
        
    updated_logs = list(logs)
    modified = False
    
    # Target agents to groom
    target_agents = [
        ("docs agent", "Docs Agent"),
        ("knowledge agent", "Docs Agent"),
        ("sql agent", "SQL Agent"),
        ("database agent", "SQL Agent"),
        ("code agent", "Code Agent"),
        ("ticket agent", "Ticket Agent"),
        ("ticket_agent", "Ticket Agent")
    ]
    
    for i, log in enumerate(updated_logs):
        log_lower = log.lower()
        
        # We only groom long results (> 150 chars) and make sure we don't re-groom an already groomed log
        if len(log) > 150 and "[log groomer]" not in log_lower and "groomed" not in log_lower:
            # Determine which agent this log belongs to
            matching_agent_label = None
            for kw, label in target_agents:
                if kw in log_lower:
                    matching_agent_label = label
                    break
            
            # We groom if it matches one of our target agents and has success/error results
            if matching_agent_label and ("success" in log_lower or "result" in log_lower or "found" in log_lower):
                print(f"[Log Groomer] Compressing log entry {i} of length {len(log)} for {matching_agent_label}...")
                
                system_prompt = (
                    "You are a Log Summarizer. Convert the raw agent output/results into a single, "
                    "extremely short semantic summary (under 20 words).\n"
                    "Preserve critical names, dates, numbers, GPAs, and key facts.\n"
                    "Do not include markdown or JSON formatting. Respond with only the summary text."
                )
                prompt = f"Raw Agent Log:\n{log}\n\nConcisely summarize the results:"
                
                # Query LLM (will silently use fast qwen3:0.6b under 2 seconds)
                summary = query_llm(prompt, system_prompt)
                summary = summary.strip().replace("\n", " ")
                
                # Safe guard if LLM fails, returns empty/error, or returns raw JSON
                if summary and len(summary) < len(log) and not (summary.startswith("{") and summary.endswith("}")):
                    new_log = f"[Log Groomer] [{matching_agent_label} SUCCESS (Groomed)] {summary}"
                    updated_logs[i] = new_log
                    modified = True
                    print(f"[Log Groomer] New summary: '{new_log}'")
                else:
                    # Simple local non-LLM crop fallback if LLM response was invalid or failed
                    lines = log.replace("\\n", "\n").split("\n")
                    cropped = " ".join([line.strip() for line in lines if line.strip()][:3])
                    if len(cropped) > 120:
                        cropped = cropped[:117] + "..."
                    new_log = f"[Log Groomer] [{matching_agent_label} SUCCESS (Groomed Fallback)] {cropped}"
                    updated_logs[i] = new_log
                    modified = True
                    print(f"[Log Groomer] Fallback crop summary: '{new_log}'")

    if modified:
        return {"logs": updated_logs}
    return {}
