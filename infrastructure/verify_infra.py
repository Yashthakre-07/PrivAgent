import socket
import urllib.request
import json
import os

# Load variables from .env file manually to keep it simple and dependency-free
def load_env():
    env_vars = {}
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

ENV = load_env()

# Helper function to check if a TCP port is open (Zero dependencies)
def check_port(host, port, service_name):
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            print(f"[OK] {service_name} (Port {port}): TCP connection successful.")
            return True
    except Exception as e:
        print(f"[FAIL] {service_name} (Port {port}): Failed to connect. Error: {e}")
        return False

# Helper function to test HTTP endpoints (Zero dependencies)
def check_http(url, service_name):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status == 200:
                print(f"[OK] {service_name} HTTP Endpoint ({url}): Status 200 OK.")
                return True
    except Exception as e:
        print(f"[FAIL] {service_name} HTTP Endpoint ({url}): Unreachable. Error: {e}")
    return False

def main():
    print("=" * 60)
    print("           PRIVAGENT INFRASTRUCTURE CHECKER           ")
    print("=" * 60)

    # 1. PostgreSQL (Check port)
    postgres_port = ENV.get("POSTGRES_PORT", 5432)
    postgres_ok = check_port("localhost", postgres_port, "PostgreSQL")

    # 2. Qdrant (Check port and HTTP status endpoint)
    qdrant_port = ENV.get("QDRANT_PORT", 6333)
    qdrant_tcp = check_port("localhost", qdrant_port, "Qdrant Vector DB")
    if qdrant_tcp:
        check_http(f"http://localhost:{qdrant_port}/readyz", "Qdrant Ready Check")

    # 3. Neo4j (Check port and HTTP login page)
    neo4j_port = ENV.get("NEO4J_PORT_HTTP", 7474)
    neo4j_tcp = check_port("localhost", neo4j_port, "Neo4j Graph DB")
    if neo4j_tcp:
        check_http(f"http://localhost:{neo4j_port}", "Neo4j Console")

    # 4. Ollama (Check port and model tags endpoint)
    ollama_port = ENV.get("OLLAMA_PORT", 11434)
    ollama_tcp = check_port("localhost", ollama_port, "Ollama LLM Runner")
    if ollama_tcp:
        # Check standard endpoint that lists downloaded local models
        tags_url = f"http://localhost:{ollama_port}/api/tags"
        try:
            with urllib.request.urlopen(tags_url, timeout=3) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    models = [m['name'] for m in data.get('models', [])]
                    print(f"[OK] Ollama API is alive. Available models: {models}")
                else:
                    print(f"[WARN] Ollama API returned status {response.status}")
        except Exception as e:
            print(f"[FAIL] Ollama API request failed: {e}")

    print("=" * 60)

if __name__ == "__main__":
    main()
