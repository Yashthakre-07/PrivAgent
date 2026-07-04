import glob
import re
import os
import json
from src.state import AgentState

def code_agent_node(state: AgentState) -> dict:
    """Scans local workspace files for keyword occurrences, simulating code parsing and regex analysis."""
    idx = state["current_task_index"]
    task = state["plan"][idx]
    print(f"\n--- [Code Agent] Querying Repository: {task['task']} ---")
    
    logs = state.get("logs", [])
    query = task["task"]
    
    # Extract search terms from task description (words in quotes, or key identifiers)
    keywords = re.findall(r"['\"](\w+)['\"]", query)
    if not keywords:
        # Fallback: extract terms > 4 chars, excluding typical task stopwords
        stopwords = {"query", "database", "retrieve", "analyze", "document", "summary", "write", "check", "support", "ticket"}
        keywords = [w for w in query.replace(".", "").replace(",", "").lower().split() if len(w) > 4 and w not in stopwords]
        
    print(f"[Code Agent] Extracted search keywords: {keywords}")
    
    matches = []
    # Search all python, markdown, and env configuration files in the current folder structure
    patterns = ["*.md", "src/**/*.py", "src/*.py", "infrastructure/*"]
    
    for pattern in patterns:
        for filepath in glob.glob(pattern, recursive=True):
            if os.path.isfile(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            for kw in keywords:
                                if kw.lower() in line.lower():
                                    matches.append({
                                        "file": filepath,
                                        "line_num": line_num,
                                        "snippet": line.strip()[:100],  # Keep output clean and short
                                        "match": kw
                                    })
                except Exception:
                    continue # Ignore encoding or read issues
                    
    # Cap results for clarity and ease of reading
    results = matches[:5]
    formatted = json.dumps(results, indent=2) if results else "No keyword matches found in workspace files."
    print(f"[Code Agent] Found {len(matches)} occurrences. Showing top {len(results)} matches.")
    
    return {
        "current_task_index": idx + 1,
        "logs": logs + [f"[Code Agent SUCCESS] Repository scan results: {formatted}"]
    }
