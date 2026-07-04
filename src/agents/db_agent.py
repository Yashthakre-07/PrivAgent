import psycopg
import json
from src.state import AgentState
from src.agents.intent_agent import query_llm

DB_URI = "postgresql://privagent:privagent_secure_pass_99@127.0.0.1:5432/privagent_db"

def init_db():
    """Initializes the mock database tables and inserts demo data."""
    with psycopg.connect(DB_URI, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            # Create a mock customer churn data table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS churn_data (
                    id SERIAL PRIMARY KEY,
                    client_name VARCHAR(100) NOT NULL,
                    region VARCHAR(50),
                    churn_date DATE,
                    reason VARCHAR(255),
                    revenue_loss NUMERIC
                );
            """)
            
            # Check if table already has data
            cur.execute("SELECT COUNT(*) FROM churn_data;")
            if cur.fetchone()[0] == 0:
                print("[DB Agent] Seeding mock customer churn data...")
                cur.execute("""
                    INSERT INTO churn_data (client_name, region, churn_date, reason, revenue_loss) VALUES
                    ('AcmeCorp', 'East', '2026-05-12', 'Competitor pricing and billing bugs', 50000.00),
                    ('Globex', 'West', '2026-06-01', 'Poor customer support turnaround', 35000.00),
                    ('Initech', 'East', '2026-02-15', 'Frequent database connection downtimes', 12000.00),
                    ('Hooli', 'South', '2026-04-20', 'Shift in corporate strategy and pricing issues', 80000.00);
                """)
                conn.commit()

def db_agent_node(state: AgentState) -> dict:
    """Uses LLM to write SQL, executes it against PostgreSQL, and returns outcomes."""
    idx = state["current_task_index"]
    task = state["plan"][idx]
    print(f"\n--- [Database Agent] Executing: {task['task']} ---")
    
    # 1. Ensure table and data exist
    use_fallback = False
    try:
        init_db()
    except Exception as e:
        print(f"[Database Agent] PostgreSQL connection failed ({e}). Falling back to local data query...")
        use_fallback = True
        
    # Simple check for our simulated error flow
    if "fail" in task["task"].lower():
         return {"errors": state.get("errors", []) + ["SQL Agent failed: Simulating execution failure."]}
         
    logs = state.get("logs", [])
    
    if use_fallback:
        # Local mock database entries
        CHURN_DATA = [
            {"client_name": "AcmeCorp", "region": "East", "churn_date": "2026-05-12", "reason": "Competitor pricing and billing bugs", "revenue_loss": 50000.00},
            {"client_name": "Globex", "region": "West", "churn_date": "2026-06-01", "reason": "Poor customer support turnaround", "revenue_loss": 35000.00},
            {"client_name": "Initech", "region": "East", "churn_date": "2026-02-15", "reason": "Frequent database connection downtimes", "revenue_loss": 12000.00},
            {"client_name": "Hooli", "region": "South", "churn_date": "2026-04-20", "reason": "Shift in corporate strategy and pricing issues", "revenue_loss": 80000.00}
        ]
        results = []
        task_lower = task["task"].lower()
        has_keywords = any(kw in task_lower for kw in ["q2", "acme", "globex", "initech", "hooli", "churn", "sales", "revenue", "loss", "customer"])
        
        if has_keywords:
            for row in CHURN_DATA:
                if "q2" in task_lower:
                    if "2026-04" in row["churn_date"] or "2026-05" in row["churn_date"] or "2026-06" in row["churn_date"]:
                        results.append(row)
                elif "acme" in task_lower:
                    if "acmecorp" in row["client_name"].lower():
                        results.append(row)
                elif "globex" in task_lower:
                    if "globex" in row["client_name"].lower():
                        results.append(row)
                elif "initech" in task_lower:
                    if "initech" in row["client_name"].lower():
                        results.append(row)
                elif "hooli" in task_lower:
                    if "hooli" in row["client_name"].lower():
                        results.append(row)
                else:
                    results.append(row)
        
        if "update" in task_lower and has_keywords:
            msg = "[DB Agent SUCCESS (Fallback)] Simulated updating database row: AcmeCorp revenue_loss updated to 60000.00."
        elif "delete" in task_lower and has_keywords:
            msg = "[DB Agent SUCCESS (Fallback)] Simulated deleting database row."
        elif results:
            msg = f"[DB Agent SUCCESS (Fallback)] Local query results: {json.dumps(results, default=str)}"
        else:
            msg = "[DB Agent SUCCESS (Fallback)] No relevant database records found for this query."
            
        print(f"[Database Agent] Local query completed.")
        return {
            "current_task_index": idx + 1,
            "logs": logs + [msg],
            "approved": False
        }

    # 2. Ask LLM to generate SQL based on the task description
    schema_info = (
        "Table name: churn_data\n"
        "Columns:\n"
        "  - client_name (VARCHAR)\n"
        "  - region (VARCHAR)\n"
        "  - churn_date (DATE) -- Q2 2026 dates fall between '2026-04-01' and '2026-06-30'\n"
        "  - reason (VARCHAR)\n"
        "  - revenue_loss (NUMERIC)\n"
    )
    
    system_prompt = (
        "You are the Database Agent for PrivAgent.\n"
        f"Given the database schema:\n{schema_info}\n"
        "Write a standard PostgreSQL SELECT query to satisfy the request.\n"
        "Respond with the raw SQL query and nothing else. Do not wrap in markdown syntax.\n"
        "Example output:\n"
        "SELECT * FROM churn_data WHERE region = 'East';"
    )
    
    prompt = f"Write SQL for: {task['task']}"
    sql_query = query_llm(prompt, system_prompt).replace("```sql", "").replace("```", "").strip()
    print(f"[Database Agent] Generated SQL: {sql_query}")
    
    # 3. Execute SQL Query
    try:
        with psycopg.connect(DB_URI, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query)
                if cur.description is not None:
                    columns = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                    results = [dict(zip(columns, row)) for row in rows]
                    formatted_results = json.dumps(results, default=str)
                else:
                    results = {"rows_affected": cur.rowcount}
                    formatted_results = json.dumps(results)
                    
                print(f"[Database Agent] SQL executed successfully.")
                return {
                    "current_task_index": idx + 1,
                    "logs": logs + [f"[DB Agent SUCCESS] SQL Executed: {sql_query} | Result: {formatted_results}"],
                    "approved": False
                }
    except Exception as e:
        print(f"[Database Agent] SQL Error: {e}")
        return {"errors": state.get("errors", []) + [f"SQL Execution Error: {e}"]}
