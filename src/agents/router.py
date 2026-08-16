import json
import urllib.request
import os
import inspect
from src.state import AgentState

def get_env_val(key: str, default: str = None) -> str:
    """Dynamically loads configuration from system environment variables or infrastructure/.env."""
    val = os.environ.get(key)
    if val:
        return val
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "infrastructure", ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#") or "=" not in stripped:
                        continue
                    k, v = stripped.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
    except Exception:
        pass
    return default

OLLAMA_BASE_URL = get_env_val("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
MODEL_NAME = "gemma4:latest"
ACTIVE_MODEL = None

# --- In-Memory Semantic Query Cache ---
QUERY_CACHE = {}

def get_cached_response(query: str) -> dict:
    """Returns cached response if present and valid, allowing sub-50ms query fulfillment."""
    key = query.strip().lower()
    cached = QUERY_CACHE.get(key)
    if cached and cached.get("response") and len(cached.get("response", "").strip()) > 30 and not cached.get("response").startswith("{") and "Hello! How can I assist" not in cached.get("response"):
        return cached
    return None

def set_cached_response(query: str, response: str, pathway: str = "CACHE"):
    """Caches query response in memory."""
    key = query.strip().lower()
    QUERY_CACHE[key] = {
        "response": response,
        "pathway": pathway,
        "is_cached": True
    }

def get_available_model() -> str:
    """Queries local Ollama tags to find an installed non-embedding model."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as res:
            data = json.loads(res.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", []) if "embed" not in m["name"].lower()]
            if models:
                return models[0]
    except Exception:
        pass
    return "gemma4:latest"

from src.sk_router import sk_router

def query_llm(prompt: str, system_prompt: str, state_to_append_logs: dict = None, model: str = None, max_tokens: int = 512, timeout: int = 12) -> str:
    """Helper to query LLM via Semantic Kernel Router with automatic Azure OpenAI fallback."""
    selected_model = model if model else (ACTIVE_MODEL if ACTIVE_MODEL else get_available_model())
    
    if state_to_append_logs is not None and "logs" in state_to_append_logs:
        caller = inspect.currentframe().f_back.f_code.co_name
        agent_display_name = caller.replace("_node", "").replace("_agent", "").upper()
        state_to_append_logs["logs"].append(f"[{agent_display_name} THINKING] SK-Router Model: {selected_model} | System Prompt: {system_prompt[:120]}...")

    res = sk_router.query_with_fallback(
        prompt=prompt,
        system_prompt=system_prompt,
        target_model=selected_model,
        state_to_append_logs=state_to_append_logs,
        agent_name=agent_display_name if 'agent_display_name' in locals() else "Agent"
    )
    return res if res else "{}"


# --- 1. SECURITY AGENT NODE ---
def security_agent_node(state: AgentState) -> dict:
    """Intercepts user query and checks role permissions and safety rules."""
    user_query = state.get("user_query", "")
    user_role = state.get("user_role", "guest")
    logs = state.get("logs", [])
    
    print("\n--- [Security Agent] Auditing Prompt Safety & RBAC ---")
    restricted_keywords = ["drop table", "sudo", "truncate", "rm -rf", "shutdown", "grant all"]
    query_lower = user_query.lower()
    
    if user_role != "admin" and any(kw in query_lower for kw in restricted_keywords):
        block_msg = f"[SECURITY BLOCK] Query contains restricted operations ({user_query}) forbidden for role '{user_role}'."
        print(f"[Security Agent] {block_msg}")
        return {
            "final_response": block_msg,
            "logs": logs + [block_msg]
        }
    
    print("[Security Agent] Safety checks passed.")
    return {"logs": logs + [f"[Security Agent SUCCESS] Prompt cleared for role '{user_role}'."]}

# --- 2. INTENT ROUTER NODE ---
def intent_agent_node(state: AgentState) -> dict:
    """Classifies user query into required investigator capabilities and 3-Pathway system."""
    global ACTIVE_MODEL
    selected = state.get("selected_model")
    ACTIVE_MODEL = selected if selected else MODEL_NAME
    print(f"[Intent Agent] Active model set to: {ACTIVE_MODEL}")
    print("\n--- [Intent Agent] Classifying User Goal ---")
    
    user_query = state.get("user_query", "")
    logs = state.get("logs", [])
    
    # 0. Check Semantic Memory Cache for sub-50ms fulfillment
    cached = get_cached_response(user_query)
    if cached:
        print("[Intent Agent] CACHE HIT! Fulfilling query instantly from memory cache.")
        intent_dict = {
            "requires_sql": False, "requires_docs": False, "requires_code": False, "requires_tickets": False,
            "pathway": "PATHWAY_CACHE", "target_agent": None, "cached_response": cached["response"]
        }
        return {
            "intent": intent_dict,
            "draft_response": cached["response"],
            "logs": logs + ["[Intent Agent SUCCESS] Fulfilled via Semantic Memory Cache (< 50ms)."]
        }
    
    query_clean = user_query.strip().lower().rstrip("?.! ")
    greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "."]
    if query_clean in greetings:
        print("[Intent Agent] Greeting bypass active. Instantly setting no resources required.")
        intent_dict = {
            "requires_sql": False, "requires_docs": False, "requires_code": False, "requires_tickets": False,
            "pathway": "PATHWAY_1", "target_agent": None
        }
        return {"intent": intent_dict, "logs": logs + ["[Intent Agent SUCCESS] Classification bypassed for simple greeting."]}
        
    system_prompt = (
        "You are the Intent Agent for PrivAgent.\n"
        "Classify enterprise resources needed to answer the user request.\n"
        "Respond with a raw JSON object and nothing else:\n"
        '{\n  "requires_sql": true/false,\n  "requires_docs": true/false,\n  "requires_code": true/false,\n  "requires_tickets": true/false\n}'
    )
    prompt = f"User Request: {user_query}\nDetermine required resources and output JSON:"
    state_logs = {"logs": list(logs)}
    raw_response = query_llm(prompt, system_prompt, state_to_append_logs=state_logs, max_tokens=64, timeout=2)
    
    try:
        cleaned = raw_response.replace("```json", "").replace("```", "").strip()
        intent_dict = json.loads(cleaned)
        if not isinstance(intent_dict, dict):
            raise ValueError("Intent must be a dict.")
    except Exception:
        intent_dict = {"requires_sql": False, "requires_docs": False, "requires_code": False, "requires_tickets": False}

    query_clean = user_query.lower().replace(".", "").replace(",", "").replace("?", "").replace("!", "").replace(":", "")
    query_words = set(query_clean.split())
    
    if any(kw in query_words or kw in query_clean for kw in {"doc", "docs", "documentation", "strategy", "manual", "guide", "incident", "pdf", "file", "post-mortem", "read", "notes", "cgpa", "grade", "gpa", "boy", "student", "transcript", "certificate", "resume", "cv", "yash", "thakre", "biologicale"}):
        intent_dict["requires_docs"] = True

    if (any(kw in query_words for kw in {"db", "sql", "database", "table", "customer", "revenue", "loss", "records", "intech", "acmecorp", "churn", "sales"}) or any(phrase in query_clean for phrase in ["delete customer", "delete record", "update customer"])) and not any(kw in query_words for kw in {"gpa", "cgpa", "transcript", "cv", "resume"}):
        intent_dict["requires_sql"] = True

    if any(kw in query_words or kw in query_clean for kw in {"code", "repo", "repository", "files", "python", "javascript", "function", "run_query", "src", "api.py", "git", "class"}):
        intent_dict["requires_code"] = True

    if any(kw in query_words or kw in query_clean for kw in {"ticket", "tickets", "jira", "issues", "support", "bug"}):
        intent_dict["requires_tickets"] = True

    if any(kw in query_words or kw in query_clean for kw in {"search", "web", "duckduckgo", "google", "online", "news", "latest", "weather", "current", "who", "modi", "pm", "president", "india", "minister", "biography", "about"}) or not (intent_dict.get("requires_sql") or intent_dict.get("requires_docs") or intent_dict.get("requires_code") or intent_dict.get("requires_tickets")):
        intent_dict["requires_web"] = True

    active_tools = []
    if intent_dict.get("requires_sql"): active_tools.append("sql_agent")
    if intent_dict.get("requires_docs"): active_tools.append("docs_agent")
    if intent_dict.get("requires_code"): active_tools.append("code_agent")
    if intent_dict.get("requires_tickets"): active_tools.append("ticket_agent")
    if intent_dict.get("requires_web"): active_tools.append("web_search_agent")

    if len(active_tools) == 0:
        intent_dict["pathway"] = "PATHWAY_1"
        intent_dict["target_agent"] = None
    elif len(active_tools) == 1:
        intent_dict["pathway"] = "PATHWAY_2"
        intent_dict["target_agent"] = active_tools[0]
    else:
        intent_dict["pathway"] = "PATHWAY_3"
        intent_dict["target_agent"] = active_tools

    print(f"[Intent Agent] Parsed Intent: {intent_dict} | Pathway: {intent_dict['pathway']}")
    return {"intent": intent_dict, "logs": state_logs["logs"]}

# --- 3. PLANNING AGENT NODE ---
def planning_agent_node(state: AgentState) -> dict:
    """Decomposes intent into a structured task execution plan for Pathway 3."""
    print("\n--- [Planning Agent] Generating Dynamic Execution Plan ---")
    user_query = state.get("user_query", "")
    intent = state.get("intent", {})
    logs = state.get("logs", [])
    errors = state.get("errors", [])
    current_plan = state.get("plan", [])
    current_idx = state.get("current_task_index", 0)
    
    if errors:
        latest_error = errors[-1]
        print(f"[Planning Agent] Replanning due to execution error: {latest_error}")
        new_plan = list(current_plan)
        if current_idx < len(new_plan):
            failed_task = new_plan[current_idx]
            new_plan[current_idx] = {
                "task": f"RETRY: {failed_task['task']} (Avoid: {latest_error[:80]})",
                "agent": failed_task["agent"]
            }
        return {"plan": new_plan, "logs": logs + [f"[Planning Agent REPLAN] Modifying task {current_idx} after error: {latest_error}"]}

    # If plan already exists and tasks are in progress, just return existing plan to continue execution
    if current_plan and current_idx > 0:
        print(f"[Planning Agent] Plan already in progress (task {current_idx}/{len(current_plan)}). Resuming.")
        return {"plan": current_plan, "logs": logs + [f"[Planning Agent] Resuming existing plan at task {current_idx}."]}

    req_sql = intent.get("requires_sql", False)
    req_docs = intent.get("requires_docs", False)
    req_code = intent.get("requires_code", False)
    req_tickets = intent.get("requires_tickets", False)
    
    system_prompt = (
        "You are the Planning Agent for PrivAgent.\n"
        "Decompose the user goal into a JSON array of task objects.\n"
        "Valid agent names: 'sql_agent', 'docs_agent', 'code_agent', 'ticket_agent'.\n"
        "Format: [{'task': '...', 'agent': '...'}]"
    )
    prompt = f"User Request: {user_query}\nRequired Resources: SQL={req_sql}, Docs={req_docs}, Code={req_code}, Tickets={req_tickets}\nOutput JSON task plan:"
    state_logs = {"logs": list(logs)}
    raw_response = query_llm(prompt, system_prompt, state_to_append_logs=state_logs, max_tokens=128, timeout=2)
    
    try:
        cleaned = raw_response.replace("```json", "").replace("```", "").strip()
        plan = json.loads(cleaned)
        if not isinstance(plan, list): raise ValueError("Plan must be a list")
    except Exception:
        plan = []
        if req_sql: plan.append({"task": f"Query database for details related to: {user_query}", "agent": "sql_agent"})
        if req_docs: plan.append({"task": f"Search document repository for: {user_query}", "agent": "docs_agent"})
        if req_code: plan.append({"task": f"Search code repository for: {user_query}", "agent": "code_agent"})
        if req_tickets: plan.append({"task": f"Search support tickets for: {user_query}", "agent": "ticket_agent"})
        if intent.get("requires_web", False): plan.append({"task": user_query, "agent": "web_search_agent"})
        
    print(f"[Planning Agent] Generated Plan ({len(plan)} tasks): {plan}")
    return {"plan": plan, "current_task_index": 0, "logs": state_logs["logs"] + [f"[Planning Agent SUCCESS] Created execution plan with {len(plan)} tasks."]}
