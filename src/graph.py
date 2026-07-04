import psycopg
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from src.state import AgentState
from src.agents.intent_agent import intent_agent_node
from src.agents.planning_agent import planning_agent_node

# PostgreSQL connection string matching Phase 1 credentials
DB_URI = "postgresql://privagent:privagent_secure_pass_99@127.0.0.1:5432/privagent_db"

# Import real investigator agent nodes (Phase 3 actual tool logic)
from src.agents.db_agent import db_agent_node
from src.agents.docs_agent import docs_agent_node
from src.agents.code_agent import code_agent_node
from src.agents.ticket_agent import ticket_agent_node
from src.agents.security_agent import security_agent_node
from src.agents.human_agent import human_approval_node

# Import Analyst and Critic nodes
from src.agents.analyst_agent import analyst_agent_node
from src.agents.critic_agent import critic_agent_node
from src.agents.log_groomer import log_groomer_node

# 3. Router logic
def security_router(state: AgentState):
    """Routes state based on whether Security Agent blocked the query."""
    if "SECURITY BLOCK" in state.get("final_response", ""):
        print("--> [Router] Security block active. Routing to END.")
        return END
    return "intent_agent"

def execution_router(state: AgentState):
    """Routes state to the appropriate node based on planning, errors, and approvals."""
    errors = state.get("errors", [])
    plan = state.get("plan", [])
    idx = state.get("current_task_index", 0)
    approved = state.get("approved", False)
    
    # If a new error has been thrown and not yet resolved, route to planner for replanning
    if errors and len(errors) > len([l for l in state.get("logs", []) if "replan" in l.lower()]):
        print("--> [Router] Error detected. Routing to Planning Agent for replanning.")
        return "planning_agent"
        
    # Check if there are still tasks left in the plan
    if idx < len(plan):
        next_agent = plan[idx]["agent"]
        task_desc = plan[idx]["task"].lower()
        
        # Intercept modifying tasks for human-in-the-loop approval
        write_keywords = ["update", "delete", "drop", "create", "insert", "modify", "recreate"]
        is_write_task = any(kw in task_desc for kw in write_keywords)
        
        if is_write_task and not approved:
            print(f"--> [Router] Task {idx} is a write operation. Routing to Human Approval gate.")
            return "human_approval"
            
        print(f"--> [Router] Routing task {idx} to: {next_agent}")
        return next_agent
        
    print("--> [Router] Plan completed. Routing to Analyst Agent.")
    return "analyst_agent"

def critic_router(state: AgentState):
    """Loops back to the Analyst if Critic finds issues, unless retry limit is reached."""
    feedback = state.get("critic_feedback", "")
    retry_count = state.get("retry_count", 0)
    
    # Check if Critic passed (we allow "PASS" case-insensitive)
    if feedback.strip().upper().startswith("PASS"):
        print("--> [Router] Critic PASSED the draft. Routing to final_answer.")
        return "final_answer"
    
    # If Critic flagged issues, check retry limit
    if retry_count < 2:
        print(f"--> [Router] Critic flagged issues. Retry count {retry_count} < 2. Routing to analyst_agent for refinement.")
        return "analyst_agent"
    
    print(f"--> [Router] Critic flagged issues, but retry count {retry_count} reached maximum of 2. Routing to final_answer anyway.")
    return "final_answer"

def final_answer_node(state: AgentState) -> dict:
    """Takes the approved Analyst draft response and promotes it to the final user answer."""
    print("\n--- [Final Answer Agent] Promoting Draft to Final Response ---")
    draft = state.get("draft_response", "")
    return {
        "final_response": draft
    }

# 4. Building the StateGraph workflow
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("security_agent", security_agent_node)
workflow.add_node("intent_agent", intent_agent_node)
workflow.add_node("planning_agent", planning_agent_node)
workflow.add_node("sql_agent", db_agent_node)
workflow.add_node("docs_agent", docs_agent_node)
workflow.add_node("code_agent", code_agent_node)
workflow.add_node("ticket_agent", ticket_agent_node)
workflow.add_node("analyst_agent", analyst_agent_node)
workflow.add_node("critic_agent", critic_agent_node)
workflow.add_node("final_answer", final_answer_node)
workflow.add_node("human_approval", human_approval_node)
workflow.add_node("log_groomer", log_groomer_node)

# Add edges
workflow.add_edge(START, "security_agent")
workflow.add_conditional_edges("security_agent", security_router)
workflow.add_edge("intent_agent", "planning_agent")

# Planning Agent points to the router which decides whether to do task execution, replan, or synthesize
workflow.add_conditional_edges("planning_agent", execution_router)

# Investigator nodes all route to log_groomer, which compresses raw outputs, then routes back to planning_agent
workflow.add_edge("sql_agent", "log_groomer")
workflow.add_edge("docs_agent", "log_groomer")
workflow.add_edge("code_agent", "log_groomer")
workflow.add_edge("ticket_agent", "log_groomer")
workflow.add_edge("log_groomer", "planning_agent")

# Human approval routes back to planning agent (to pass through to router again)
workflow.add_edge("human_approval", "planning_agent")

# New Analyst-Critic flow edges
workflow.add_edge("analyst_agent", "critic_agent")
workflow.add_conditional_edges("critic_agent", critic_router)
workflow.add_edge("final_answer", END)

import threading

_cached_graph = None
_graph_lock = threading.Lock()

# Helper function to get compiled graph with Postgres checkpointer, falling back to MemorySaver if offline
def get_graph():
    global _cached_graph
    if _cached_graph is not None:
        return _cached_graph
        
    with _graph_lock:
        if _cached_graph is not None:
            return _cached_graph
            
        try:
            # Connect directly to Postgres with a 3 second timeout
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
