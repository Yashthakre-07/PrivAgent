from src.state import AgentState
from src.agents.intent_agent import query_llm

def analyst_agent_node(state: AgentState) -> dict:
    """Synthesizes all gathered investigator findings into a draft answer, incorporating critic feedback if present."""
    print("\n--- [Analyst Agent] Formulating Draft Response ---")
    
    logs = state.get("logs", [])
    user_query = state.get("user_query", "")
    critic_feedback = state.get("critic_feedback", "")
    current_draft = state.get("draft_response", "")
    retry_count = state.get("retry_count", 0)
    
    system_prompt = (
        "You are the Analyst Agent for PrivAgent.\n"
        "Your task is to synthesize the gathered findings from investigator logs into an incredibly detailed, comprehensive, and well-structured response.\n"
        "INSTRUCTIONS FOR EXPLANATION:\n"
        "- Explain concepts, backgrounds, and findings thoroughly (similar to ChatGPT or advanced conversational models).\n"
        "- Do not provide short summaries or single-sentence answers. Elaborate on details, context, academic background, and structural relationships.\n"
        "- Format beautifully using structured Markdown: use descriptive headings (###), bold keywords, tables, bullet points, and numbered lists.\n"
        "CRITICAL: Only include information that is directly relevant to answering the User Request. If the investigator logs contain irrelevant fallback findings (such as code file scans, connection pool tickets, or customer churn database rows that do not relate to the User Request), DO NOT include them in your final answer.\n"
        "If critic feedback is provided, you must refine and correct your previous draft to address the flagged issues.\n"
        "Ensure every statement is fully backed by the investigator logs. Structure your response logically."
    )
    
    # Filter logs to keep only investigator success outputs, reducing prompt size to prevent timeouts
    filtered_logs = []
    for l in logs:
        l_lower = l.lower()
        if "success" in l_lower and ("docs agent" in l_lower or "sql agent" in l_lower or "code agent" in l_lower or "ticket agent" in l_lower or "ticket_agent" in l_lower):
            # If the log is very large (e.g. holds full document/file contents), extract only relevant context snippets
            if len(l) > 600:
                print(f"[Analyst Agent] Extracting matching snippets from large log of length {len(l)}...")
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

    prompt = f"User Request: {user_query}\n\nInvestigator Logs:\n" + "\n".join([f"- {l}" for l in filtered_logs])
    
    if critic_feedback and current_draft:
        retry_count += 1
        print(f"[Analyst Agent] Refining previous draft (Loop {retry_count}). Critic Feedback: {critic_feedback}")
        prompt += f"\n\nPrevious Draft:\n{current_draft}\n\nCritic Feedback to address:\n{critic_feedback}\n\nPlease output the corrected and updated draft response:"
    else:
        print("[Analyst Agent] Creating initial draft response...")
        prompt += "\n\nPlease output your draft response:"
        
    state_logs = {"logs": list(logs)}
    
    # 1. Bypass LLM for simple greetings to avoid CPU speed/size echo issues
    query_clean = user_query.strip().lower().rstrip("?.! ")
    greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "."]
    if query_clean in greetings:
        draft = "Hello! I am PrivAgent, your secure enterprise orchestration assistant. How can I help you scan code repositories, query databases, check support tickets, or audit document libraries today?"
    else:
        draft = query_llm(prompt, system_prompt, state_to_append_logs=state_logs)
        
        # 2. Safety filter: If the small model echoed the intent JSON block instead of answering
        if "requires_sql" in draft or (draft.strip().startswith("{") and draft.strip().endswith("}")):
            draft = "Hello! How can I assist you with your database, files, or codebase today? Please enter a query or select one of the orchestration scenarios below."
            
    print(f"[Analyst Agent] Draft Response Generated:\n{draft[:300]}...")
    
    return {
        "draft_response": draft,
        "retry_count": retry_count,
        "logs": state_logs["logs"] + [f"[Analyst Agent] Generated/Refined draft response (Retry {retry_count})."]
    }
