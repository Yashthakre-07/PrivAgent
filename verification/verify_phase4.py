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
        print(f"Failed to query PostgreSQL checkpoints (expected if Postgres is offline): {e}")
    print("============================================\n")

def run_phase4_test():
    print("\n" + "="*80)
    print("RUNNING PHASE 4 END-TO-END ANALYST-CRITIC LOOP TEST")
    print("="*80)
    
    user_query = (
        "Retrieve customer churn records for AcmeCorp from the database, "
        "search our marketing documentation for AcmeCorp references, "
        "and reconcile whether AcmeCorp's issue is a product quality failure or pricing misalignment."
    )
    
    graph = get_graph()
    config = {"configurable": {"thread_id": "phase4_analyst_critic_thread"}}
    
    inputs = {"user_query": user_query}
    result = graph.invoke(inputs, config=config)
    
    print("\n" + "="*50)
    print("ANALYST DRAFT RESPONSE:")
    print("="*50)
    print(result.get("draft_response", "No draft response found."))
    print("="*50 + "\n")
    
    print("="*50)
    print("CRITIC AUDIT FEEDBACK:")
    print("="*50)
    print(result.get("critic_feedback", "No critic feedback found."))
    print("="*50 + "\n")
    
    print("="*50)
    print("RETRY COUNT (LOOPS):")
    print("="*50)
    print(result.get("retry_count", 0))
    print("="*50 + "\n")
    
    print("="*50)
    print("FINAL RESOLVED ANSWER:")
    print("="*50)
    print(result.get("final_response", "No response generated."))
    print("="*50 + "\n")

if __name__ == "__main__":
    run_phase4_test()
    print_checkpoints_from_db()
