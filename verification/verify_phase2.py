import psycopg
from src.graph import get_graph

# PostgreSQL connection matching graph.py
DB_URI = "postgresql://privagent:privagent_secure_pass_99@localhost:5432/privagent_db"

def print_checkpoints_from_db():
    """Queries PostgreSQL directly to print saved LangGraph checkpoints."""
    print("\n=== [PostgreSQL Checkpoint Verification] ===")
    try:
        with psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                # Query checkpoints table managed by LangGraph PostgresSaver
                cur.execute("SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints LIMIT 5;")
                rows = cur.fetchall()
                if rows:
                    print(f"Found {len(rows)} checkpoint entries in PostgreSQL database:")
                    for row in rows:
                        print(f"  - Thread ID: {row[0]}, Namespace: {row[1]}, Checkpoint ID: {row[2]}")
                else:
                    print("No checkpoints found in 'checkpoints' table yet.")
    except Exception as e:
        print(f"Failed to query PostgreSQL checkpoints: {e}")
    print("============================================\n")

def run_test_scenario(user_query: str, thread_id: str):
    print(f"\n" + "="*80)
    print(f"RUNNING SCENARIO: '{user_query}' (Thread: {thread_id})")
    print("="*80)
    
    graph = get_graph()
    
    # Configure thread configuration for PostgresSaver
    config = {"configurable": {"thread_id": thread_id}}
    
    # Invoke the compiled graph state machine
    inputs = {"user_query": user_query}
    result = graph.invoke(inputs, config=config)
    
    print("\n--- FINAL GRAPH RESPONSE ---")
    print(result.get("final_response", "No response found."))
    print("="*80 + "\n")

def main():
    # Scenario 1: Normal path (SQL and Ticket check)
    run_test_scenario(
        user_query="Please query the database for Q2 sales, check the support tickets, and write a summary.",
        thread_id="normal_run_3"
    )
    
    # Scenario 2: Error and Replanning path
    # Our mocked sql_agent triggers an error if the word 'fail' is present in the task description.
    # We ask for a task with 'fail' in the query so the planner generates a task containing the word 'fail'.
    run_test_scenario(
        user_query="Query database for a table that will fail, then analyze documentation.",
        thread_id="replan_run_3"
    )
    
    # Verify DB checkpoints
    print_checkpoints_from_db()

if __name__ == "__main__":
    main()
