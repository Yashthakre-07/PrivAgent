import json
from src.state import AgentState
from src.agents.intent_agent import query_llm

def planning_agent_node(state: AgentState) -> dict:
    """Generates the initial task list or performs replanning upon errors."""
    print("\n--- [Planning Agent] Generating Execution Plan ---")
    
    user_query = state.get("user_query", "")
    intent = state.get("intent", {})
    errors = state.get("errors", [])
    logs = state.get("logs", [])
    plan = state.get("plan", [])
    
    # If a plan already exists and there are no errors, we just pass through
    if plan and not errors:
        print("[Planning Agent] Plan already exists and no new errors found. Passing through.")
        return {}
    
    state_logs = {"logs": list(logs)}
    # 1. Check if we need to do Replanning
    if errors:
        print(f"[Planning Agent] ERROR DETECTED: {errors[-1]}. Running replanner...")
        system_prompt = (
            "You are the Planning Agent for PrivAgent.\n"
            "An error occurred in the execution of the previous plan. You must adjust the plan to recover.\n"
            "Output a JSON list of task objects, each containing: 'agent' and 'task'. Do not include markdown formatting.\n"
            "Format:\n"
            "[\n"
            '  {"agent": "docs_agent", "task": "description of recovery action"}\n'
            "]\n"
            "The 'agent' field must be exactly one of: 'sql_agent', 'docs_agent', 'code_agent', 'ticket_agent'."
        )
        prompt = f"Original Query: {user_query}\nLogs: {logs}\nLast Error: {errors[-1]}\nGenerate recovery tasks:"
        raw_response = query_llm(prompt, system_prompt, state_to_append_logs=state_logs)
    else:
        # 2. Initial Plan Generation based on Intent
        print("[Planning Agent] Generating initial plan...")
        system_prompt = (
            "You are the Planning Agent for PrivAgent.\n"
            "Create a list of sequential tasks based on the classified intent and user query.\n"
            "Output a JSON list of task objects and nothing else. Do not include markdown formatting.\n"
            "Format:\n"
            "[\n"
            '  {"agent": "agent_name", "task": "description of work"}\n'
            "]\n"
            "Use agent_names: 'sql_agent', 'docs_agent', 'code_agent', 'ticket_agent'."
        )
        
        prompt = f"Query: {user_query}\nIntent: {intent}\nGenerate task list JSON:"
        
        # 1. Bypass LLM for simple greetings to avoid CPU planning delays
        query_clean = user_query.strip().lower().rstrip("?.! ")
        greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "."]
        if query_clean in greetings:
            raw_response = "[]"
        else:
            raw_response = query_llm(prompt, system_prompt, state_to_append_logs=state_logs)
        
    print(f"[Planning Agent] Raw plan response: {raw_response}")
    
    try:
        cleaned = raw_response.replace("```json", "").replace("```", "").strip()
        plan = json.loads(cleaned)
    except Exception:
        # Fallback plan based on intent rules (easy to debug!)
        plan = []
        if intent.get("requires_sql"):
            plan.append({"agent": "sql_agent", "task": "Retrieve relevant sales or customer rows"})
        if intent.get("requires_docs"):
            plan.append({"agent": "docs_agent", "task": "Search internal PDF document repositories"})
        if intent.get("requires_code"):
            plan.append({"agent": "code_agent", "task": "Inspect repository files and directory structure"})
        if intent.get("requires_tickets"):
            plan.append({"agent": "ticket_agent", "task": "Query Jira ticket database"})
            
    print(f"[Planning Agent] Compiled Plan: {plan}")
    return {
        "plan": plan, 
        "current_task_index": 0, 
        "logs": state_logs["logs"] + [f"Generated plan with {len(plan)} tasks."],
        "errors": [] # Clear errors upon generating a new/updated plan
    }
