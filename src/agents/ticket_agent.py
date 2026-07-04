import json
import os
from src.state import AgentState

def ticket_agent_node(state: AgentState) -> dict:
    """Reads mock tickets from JSON file and performs simple keyword filtering."""
    idx = state["current_task_index"]
    task = state["plan"][idx]
    print(f"\n--- [Ticket Agent] Querying Support Tickets: {task['task']} ---")
    
    logs = state.get("logs", [])
    query = task["task"]
    
    # Locate data file
    tickets_path = os.path.join("data", "tickets.json")
    
    tickets = []
    try:
        if os.path.exists(tickets_path):
            with open(tickets_path, "r", encoding="utf-8") as f:
                tickets = json.load(f)
    except Exception as e:
        print(f"[Ticket Agent] Failed to read tickets: {e}")
        
    # Extract keywords by splitting and cleaning query terms
    clean_query = query.replace(".", "").replace(",", "").lower()
    stopwords = {"check", "query", "support", "tickets", "ticket", "inspect", "search", "history", "view"}
    search_keywords = [w for w in clean_query.split() if w not in stopwords and len(w) > 2]
    
    print(f"[Ticket Agent] Extracted query keywords: {search_keywords}")
    
    matched_tickets = []
    for ticket in tickets:
        searchable_text = (ticket.get("title", "") + " " + ticket.get("description", "")).lower()
        # Match if any keyword is a substring of the ticket details
        if any(kw in searchable_text for kw in search_keywords):
            matched_tickets.append(ticket)
            
    # Default fallback: return empty if no specific match
    if not matched_tickets:
        formatted = "No relevant support tickets found matching the query."
    else:
        formatted = json.dumps(matched_tickets, indent=2)
    print(f"[Ticket Agent] Found {len(matched_tickets)} matching tickets.")
    
    return {
        "current_task_index": idx + 1,
        "logs": logs + [f"[Ticket Agent SUCCESS] Ticket results: {formatted}"]
    }
