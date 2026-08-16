import psycopg
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from src.state import AgentState

# Import node functions from consolidated 3 modules
from src.agents.router import security_agent_node, intent_agent_node, planning_agent_node
from src.agents.investigators import db_agent_node, docs_agent_node, code_agent_node, ticket_agent_node, web_search_agent_node
from src.agents.synthesizer import analyst_agent_node, critic_agent_node, human_approval_node, log_groomer_node

# PostgreSQL connection string matching Phase 1 credentials
DB_URI = "postgresql://privagent:privagent_secure_pass_99@127.0.0.1:5432/privagent_db"

# 1. Security Router
def security_router(state: AgentState):
    """Routes state based on whether Security Agent blocked the query."""
    if "SECURITY BLOCK" in state.get("final_response", ""):
        print("--> [Router] Security block active. Routing to END.")
        return END
    return "intent_agent"

# 2. 3-Pathway Intent Router
def intent_router(state: AgentState):
    """3-Pathway Router logic after Intent Classification."""
    intent = state.get("intent", {})
    pathway = intent.get("pathway", "PATHWAY_3")
    target_agent = intent.get("target_agent")
    
    if pathway in ["PATHWAY_1", "PATHWAY_CACHE"]:
        print(f"--> [{pathway} Router] Fast Track / Cache Hit. Routing directly to Analyst Agent.")
        return "analyst_agent"
    elif pathway == "PATHWAY_2" and isinstance(target_agent, str):
        print(f"--> [Pathway 2 Router] Single Specialist Track. Routing directly to {target_agent}.")
        return target_agent
    else:
        print("--> [Pathway 3 Router] Multi-Agent Track. Routing to Planning Agent.")
        return "planning_agent"

# 3. Execution Router
def execution_router(state: AgentState):
    """Routes state to the appropriate node based on planning, errors, and approvals."""
    errors = state.get("errors", [])
    plan = state.get("plan", [])
    idx = state.get("current_task_index", 0)
    approved = state.get("approved", False)
    
    if errors and len(errors) > len([l for l in state.get("logs", []) if "replan" in l.lower()]):
        print("--> [Router] Error detected. Routing to Planning Agent for replanning.")
        return "planning_agent"
        
    if idx < len(plan):
        next_agent = plan[idx]["agent"]
        task_desc = plan[idx]["task"].lower()
        
        write_keywords = ["update", "delete", "drop", "create", "insert", "modify", "recreate"]
        is_write_task = any(kw in task_desc for kw in write_keywords)
        
        if is_write_task and not approved:
            print(f"--> [Router] Task {idx} is a write operation. Routing to Human Approval gate.")
            return "human_approval"
            
        print(f"--> [Router] Routing task {idx} to: {next_agent}")
        return next_agent
        
    print("--> [Router] Plan completed. Routing to Analyst Agent.")
    return "analyst_agent"

# 4. Groomer Router
def groomer_router(state: AgentState):
    """Routes after log grooming based on the active pathway and plan progress."""
    intent = state.get("intent", {})
    pathway = intent.get("pathway", "PATHWAY_3")
    idx = state.get("current_task_index", 0)
    plan = state.get("plan", [])
    
    if pathway in ["PATHWAY_1", "PATHWAY_2"] or idx >= len(plan) or not plan:
        print("--> [Groomer Router] Execution complete. Routing directly to Analyst Agent.")
        return "analyst_agent"
    return "planning_agent"

# 5. Critic Router
def critic_router(state: AgentState):
    """Loops back to the Analyst if Critic finds issues, unless retry limit is reached."""
    feedback = state.get("critic_feedback", "")
    retry_count = state.get("retry_count", 0)
    
    if feedback.strip().upper().startswith("PASS"):
        print("--> [Router] Critic PASSED the draft. Routing to final_answer.")
        return "final_answer"
    
    if retry_count < 2:
        print(f"--> [Router] Critic flagged issues. Retry count {retry_count} < 2. Routing to analyst_agent for refinement.")
        return "analyst_agent"
    
    print(f"--> [Router] Critic flagged issues, but retry count {retry_count} reached maximum of 2. Routing to final_answer anyway.")
    return "final_answer"

# 6. Final Answer Node
def final_answer_node(state: AgentState) -> dict:
    """Takes the approved Analyst draft response and promotes it to the final user answer."""
    print("\n--- [Final Answer Agent] Promoting Draft to Final Response ---")
    draft = state.get("draft_response", "")
    user_query = state.get("user_query", "")
    intent = state.get("intent", {})
    pathway = intent.get("pathway", "PATHWAY_3")
    
    if user_query and draft and pathway != "PATHWAY_CACHE":
        from src.agents.router import set_cached_response
        set_cached_response(user_query, draft, pathway=pathway)
        
    return {
        "final_response": draft
    }

# 7. Building the StateGraph workflow
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("security_agent", security_agent_node)
workflow.add_node("intent_agent", intent_agent_node)
workflow.add_node("planning_agent", planning_agent_node)
workflow.add_node("sql_agent", db_agent_node)
workflow.add_node("docs_agent", docs_agent_node)
workflow.add_node("code_agent", code_agent_node)
workflow.add_node("ticket_agent", ticket_agent_node)
workflow.add_node("web_search_agent", web_search_agent_node)
workflow.add_node("analyst_agent", analyst_agent_node)
workflow.add_node("critic_agent", critic_agent_node)
workflow.add_node("final_answer", final_answer_node)
workflow.add_node("human_approval", human_approval_node)
workflow.add_node("log_groomer", log_groomer_node)

# Add edges
workflow.add_edge(START, "security_agent")
workflow.add_conditional_edges("security_agent", security_router)
workflow.add_conditional_edges("intent_agent", intent_router)
workflow.add_conditional_edges("planning_agent", execution_router)

workflow.add_edge("sql_agent", "log_groomer")
workflow.add_edge("docs_agent", "log_groomer")
workflow.add_edge("code_agent", "log_groomer")
workflow.add_edge("ticket_agent", "log_groomer")
workflow.add_edge("web_search_agent", "log_groomer")
workflow.add_conditional_edges("log_groomer", groomer_router)

workflow.add_edge("human_approval", "planning_agent")
workflow.add_edge("analyst_agent", "critic_agent")
workflow.add_conditional_edges("critic_agent", critic_router)
workflow.add_edge("final_answer", END)

import threading
_cached_graph = None
_graph_lock = threading.Lock()

def get_graph():
    global _cached_graph
    if _cached_graph is not None:
        return _cached_graph
        
    with _graph_lock:
        if _cached_graph is not None:
            return _cached_graph
            
        try:
            conn = psycopg.connect(DB_URI, autocommit=True, connect_timeout=3)
            checkpointer = PostgresSaver(conn)
            checkpointer.setup()
            print("[Graph] Successfully initialized PostgreSQL checkpointer.")
            _cached_graph = workflow.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])
            return _cached_graph
        except Exception as e:
            print(f"[Graph] PostgreSQL connection failed ({e}). Falling back to global in-memory checkpointer (MemorySaver).")
            checkpointer = MemorySaver()
            _cached_graph = workflow.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])
            return _cached_graph
