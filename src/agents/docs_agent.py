import urllib.request
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models
from src.state import AgentState

import os

def get_ollama_base_url() -> str:
    # 1. Check environment variable
    url = os.environ.get("OLLAMA_BASE_URL")
    if url:
        return url.rstrip('/')
    
    # 2. Check infrastructure/.env
    try:
        # Go up 3 levels from src/agents/docs_agent.py to project root
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "infrastructure", ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    if line.strip().startswith("OLLAMA_BASE_URL="):
                        return line.strip().split("=", 1)[1].strip().rstrip('/')
    except Exception:
        pass
        
    return "http://127.0.0.1:11434"

OLLAMA_BASE_URL = get_ollama_base_url()
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embeddings"
EMBED_MODEL = "nomic-embed-text" # 768 dimensions
COLLECTION_NAME = "enterprise_docs"

# Pre-defined enterprise documentation chunks
DOCS = [
    {
        "id": 1,
        "content": "Q2 Marketing Strategy: Focus on enterprise cloud security and migration. Key competitors listed as AcmeCorp. Target regions are East and West.",
        "source": "marketing_strategy_q2.pdf"
    },
    {
        "id": 2,
        "content": "Post-Mortem May 2026: Customer billing connection timeouts resolved by fixing connection pool leaks in PostgreSQL. Increased max pool size to 50.",
        "source": "incident_post_mortem_409.pdf"
    },
    {
        "id": 3,
        "content": "PrivAgent Deployment Manual: PostgreSQL configuration files are located in /etc/privagent. PostgreSQL port is 5432, Qdrant is 6333.",
        "source": "deployment_guide.md"
    }
]

def add_document_to_context(content: str, filename: str):
    global DOCS
    # Remove any previously user-uploaded documents (keep only the 3 built-in enterprise docs)
    base_docs = [d for d in DOCS if d["id"] <= 3]
    DOCS = base_docs
    
    new_id = len(DOCS) + 1
    doc = {
        "id": new_id,
        "content": content,
        "source": filename
    }
    DOCS.append(doc)
    print(f"[Docs Agent] Replaced context with new document '{filename}' (Total documents: {len(DOCS)}).")
    
    # If Qdrant is running, also index it dynamically
    try:
        qclient = QdrantClient("http://127.0.0.1:6333", timeout=2)
        collections = qclient.get_collections().collections
        if any(c.name == COLLECTION_NAME for c in collections):
            # Remove old user-uploaded vectors (ids > 3) before inserting new one
            try:
                qclient.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="id",
                                    range=models.Range(gt=3)
                                )
                            ]
                        )
                    )
                )
            except Exception:
                pass
            
            vector = get_embedding(content)
            if vector:
                qclient.upsert(
                    collection_name=COLLECTION_NAME,
                    points=[
                        models.PointStruct(
                            id=new_id,
                            vector=vector,
                            payload={"content": content, "source": filename}
                        )
                    ]
                )
                print(f"[Docs Agent] Dynamically indexed uploaded document '{filename}' into Qdrant.")
    except Exception as e:
        print(f"[Docs Agent] Qdrant dynamic indexing skipped: {e}")

def get_embedding(text: str) -> list:
    """Queries Ollama local embeddings API for a text vector."""
    payload = {
        "model": EMBED_MODEL,
        "prompt": text
    }
    try:
        req = urllib.request.Request(
            OLLAMA_EMBED_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Bypass-Tunnel-Reminder": "true",
                "User-Agent": "localtunnel"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("embedding", [])
    except Exception as e:
        print(f"[Docs Agent] Failed to fetch vector embedding: {e}")
        return []

def init_qdrant_collection() -> QdrantClient:
    """Initializes the Qdrant vector database collection and seeds documents."""
    client = QdrantClient("http://127.0.0.1:6333", timeout=2)
    
    # Check if collection exists
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)
    
    if not exists:
        print("[Docs Agent] Creating Qdrant collection...")
        # Create collection with 768 dimensions (standard for nomic-embed-text)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
        )
        
        # Index and upload our document chunks
        points = []
        for doc in DOCS:
            vector = get_embedding(doc["content"])
            if not vector:
                print(f"[Docs Agent] Skipping vector indexing for doc {doc['id']} due to empty embedding.")
                continue
            points.append(
                models.PointStruct(
                    id=doc["id"],
                    vector=vector,
                    payload={"content": doc["content"], "source": doc["source"]}
                )
            )
            
        if points:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"[Docs Agent] Seeded {len(points)} documents into Qdrant.")
            
    return client

def docs_agent_node(state: AgentState) -> dict:
    """Performs semantic vector search on Qdrant, falling back to keyword search if down."""
    idx = state["current_task_index"]
    task = state["plan"][idx]
    print(f"\n--- [Knowledge Agent] Querying: {task['task']} ---")
    
    logs = state.get("logs", [])
    query = task["task"]
    
    # Try connecting to Qdrant
    try:
        qclient = init_qdrant_collection()
        query_vector = get_embedding(query)
        
        if query_vector:
            # Perform vector search
            search_result = qclient.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=2
            )
            
            results = []
            for hit in search_result:
                results.append({
                    "content": hit.payload["content"],
                    "source": hit.payload["source"],
                    "score": hit.score
                })
                
            formatted = json.dumps(results, indent=2)
            print(f"[Knowledge Agent] Qdrant search returned {len(results)} matches.")
            return {
                "current_task_index": idx + 1,
                "logs": logs + [f"[Docs Agent SUCCESS] Semantic search results: {formatted}"]
            }
    except Exception as e:
        print(f"[Docs Agent] Qdrant/Ollama connection failed ({e}). Falling back to simple keyword search...")
        
    # Local fallback search: simple word overlap (very clean and interview-friendly!)
    results = []
    query_words = set(query.lower().split())
    for doc in DOCS:
        doc_words = set(doc["content"].lower().replace(":", "").replace(".", "").split())
        overlap = len(query_words.intersection(doc_words))
        if overlap > 0:
            results.append({
                "content": doc["content"],
                "source": doc["source"],
                "score": overlap
            })
            
    # Sort by overlap score descending
    results = sorted(results, key=lambda x: x["score"], reverse=True)[:2]
    formatted = json.dumps(results, indent=2)
    print(f"[Knowledge Agent] Local fallback keyword search returned {len(results)} matches.")
    
    return {
        "current_task_index": idx + 1,
        "logs": logs + [f"[Docs Agent SUCCESS (Fallback)] Keyword search results: {formatted}"]
    }
