from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    user_query: str                  # The original user goal
    intent: Dict[str, Any]           # Classified intent (e.g. required capabilities/tools)
    plan: List[Dict[str, Any]]       # Generated plan (list of tasks)
    current_task_index: int          # Index of the task currently being executed
    logs: List[str]                  # Cumulative logs from all execution steps
    final_response: str              # Final synthesized answer for the user
    errors: List[str]                # Tracks execution errors to trigger replanning
    critic_feedback: str             # QA/Critic feedback on findings (optional)
    user_role: str                   # Role of the user (e.g. 'admin', 'guest')
    approved: bool                   # Whether a write task is manual-approved (HITL)
    selected_model: str              # Selected LLM model (optional)
    draft_response: str              # Draft compiled by the Analyst (optional)
    retry_count: int                 # Tracks loops between Analyst and Critic (optional)

