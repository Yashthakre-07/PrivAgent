import os
import json
import time
from datetime import datetime

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
TRACES_FILE = os.path.join(LOGS_DIR, "traces.jsonl")

def log_trace(thread_id: str, agent_name: str, message: str, latency_ms: float = None, level: str = "INFO"):
    """Logs a structured JSON trace to logs/traces.jsonl and prints to console."""
    # Ensure logs directory exists
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    trace_data = {
        "timestamp": timestamp,
        "thread_id": thread_id,
        "agent_name": agent_name,
        "message": message,
        "level": level
    }
    
    if latency_ms is not None:
        trace_data["latency_ms"] = round(latency_ms, 2)
        
    # Append structured trace to file
    try:
        with open(TRACES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_data) + "\n")
    except Exception as e:
        print(f"[Logger ERROR] Failed to write trace to file: {e}")
        
    # Print to console
    latency_str = f" [{latency_ms:.1f}ms]" if latency_ms is not None else ""
    print(f"[{timestamp}] [{level}] [{thread_id}] [{agent_name}]{latency_str} {message}")
