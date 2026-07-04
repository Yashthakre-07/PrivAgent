import psycopg
from src.graph import get_graph

DB_URI = "postgresql://privagent:privagent_secure_pass_99@127.0.0.1:5432/privagent_db"

def print_checkpoints_from_db():
    """Queries PostgreSQL directly to print saved LangGraph checkpoints."""
    print("\n=== [PostgreSQL Checkpoint Verification] ===")
    try:
        with psycopg.connect(DB_URI, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints LIMIT 5;")
                rows = cur.fetchall()
                if rows:
                    print(f"Found {len(rows)} checkpoint entries in PostgreSQL database:")
                    for row in rows:
                        print(f"  - Thread: {row[0]}, Namespace: {row[1]}, Checkpoint ID: {row[2]}")
                else:
                    print("No checkpoints found in database checkpoints table.")
    except Exception as e:
        print(f"Failed to query PostgreSQL checkpoints: {e}")
    print("============================================\n")

def run_phase3_test():
    print("\n" + "="*80)
    print("RUNNING PHASE 3 END-TO-END MULTI-AGENT TEST")
    print("="*80)
    
    # User goal that triggers ALL investigator capabilities: SQL, Tickets, Code, and Docs
    user_query = (
        "Retrieve all customer churn records for Q2 from the database, "
        "inspect the customer tickets for AcmeCorp, "
        "scan our code repository files for database configuration ports, "
        "and search our PDF documentation for port allocations."
    )
    
    graph = get_graph()
    
    # Configure session thread ID
    config = {"configurable": {"thread_id": "phase3_verification_thread"}}
    
    inputs = {"user_query": user_query}
    result = graph.invoke(inputs, config=config)
    
    print("\n--- FINAL PHASE 3 WORKFLOW RESPONSE ---")
    print(result.get("final_response", "No response generated."))
    print("="*80 + "\n")

if __name__ == "__main__":
    run_phase3_test()
    print_checkpoints_from_db()
