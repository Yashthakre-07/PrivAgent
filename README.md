# PrivAgent

PrivAgent is an on-premise, multi-agent AI orchestration engine designed for enterprises that cannot transmit sensitive, proprietary, or regulated data to external cloud-hosted LLM APIs due to strict compliance, intellectual property, or data sovereignty constraints. By running open-weight large language models locally and orchestrating task division through a self-verifying, adversarial multi-agent pipeline, PrivAgent guarantees that zero data ever leaves the enterprise perimeter while delivering highly structured, citation-grounded reasoning.

---

## Why This Project Exists

Modern enterprises operating in highly regulated spaces—such as finance, healthcare, defense, and legal services—are bound by stringent data privacy and compliance frameworks (e.g., **HIPAA**, **GDPR**, **SOC2 Type II**, **PCI-DSS**). Uploading customer logs, proprietary source code, patient records, or financial transactions to third-party cloud APIs poses significant liabilities, including:
1. **Data Leakage Risks:** The risk of feeding proprietary IP into external model training cycles or public caches.
2. **Compliance Violations:** Explicit regulatory prohibitions against sending customer PII to cloud boundaries without strict geographic zoning.
3. **Black-box Hallucinations:** Traditional single-pass RAG systems often produce plausible-sounding hallucinations without systematic verification, making them too risky for auditable decision-making.

PrivAgent resolves these liabilities by running **100% locally** (from ingestion to consensus) while implementing a verifiable multi-agent graph with explicit human-in-the-loop (HITL) gate controls.

---

## System Architecture & Workflow

PrivAgent uses a stateful, cyclic execution graph powered by **LangGraph**. Unlike standard linear RAG pipelines, every user query triggers a five-stage verification cycle.

```
       [ START ]
           │
           ▼
┌──────────────────────┐
│  Security Gate Check │ ◄── (security_agent.py: PII, RBAC, input sanitization)
└──────────┬───────────┘
           │ (Pass)
           ▼
┌──────────────────────┐
│  Intent & Planning   │ ◄── (intent_agent.py & planning_agent.py: Task Generation)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Orchestrated Nodes  │ ◄── (Runs specialists in parallel/sequence:
└────┬─────┬─────┬─────┘      db_agent.py, docs_agent.py, code_agent.py, ticket_agent.py)
     │     │     │
     ▼     ▼     ▼
┌──────────────────────┐
│  Adversarial Debate  │ ◄── (analyst_agent.py drafts, critic_agent.py audits correctness)
└──────────┬───────────┘
           │ (Loop back if fails Critic check, max 2 retries)
           ▼
┌──────────────────────┐
│   Final Consensus    │ ◄── (final_answer_node: Promotes checked draft with citations)
└──────────┬───────────┘
           │
           ▼
        [ END ]
```

### Stage 1: Security Gate Check (`security_agent.py`)
Intercepts raw user prompts before they reach the LLM. It screens for prompt-injection vectors, sanitizes PII (such as emails, phone numbers, and credentials), and verifies user access roles (Admin/Guest) against execution permissions.

### Stage 2: Intent & Planning Agent (`intent_agent.py` & `planning_agent.py`)
Classifies the intent of the query and dynamically compiles a sequential execution plan. Complex queries are broken down into granular, tool-specific sub-tasks.

### Stage 3: Orchestrated Node Execution
Dynamically routes sub-tasks across specialized workspace agents equipped with local tools:
*   **Database Agent (`db_agent.py`):** Translates tasks into SQL queries, interfacing with structured PostgreSQL databases.
*   **Knowledge Agent (`docs_agent.py`):** Performs local vector embeddings search and extracts context from unstructured document repositories.
*   **Codebase Agent (`code_agent.py`):** Analyzes repository directory structures and source code files.
*   **Ticket Agent (`ticket_agent.py`):** Queries internal support ticket tracking databases.

### Stage 4: Adversarial Debate Synthesis (`analyst_agent.py` & `critic_agent.py`)
To prevent hallucinations, the **Analyst Agent** synthesizes findings from Stage 3 into a draft. The **Critic Agent** audits the draft line-by-line against the raw investigator logs. If claims are made that are not backed by raw logs, the Critic flags the discrepancies and routes execution back to the Analyst for refinement.

### Stage 5: Verification & Final Consensus (`final_answer_node`)
Once the Critic issues a `PASS`, the draft is promoted to the final response. It is formatted with citations pointing back to the specific source documents, providing an auditable trace.

---

## Key Engineering Decisions

### 1. Local Inference (Ollama/Gemma) vs. Cloud APIs (OpenAI/Anthropic)
*   **Trade-off:** Cloud APIs offer higher parameter counts and lower local resource requirements, but violate data sovereignty.
*   **Decision:** We run local open-weight models via **Ollama** with a fallback pipeline. To prevent CPU memory swapping and execution timeouts in resource-constrained environments, `gemma4:latest` is mapped internally to a lightweight instruction-tuned local model (`qwen3:0.6b`), maintaining fast inference speeds locally.

### 2. Stateful Multi-Agent Graph vs. Single-Agent RAG
*   **Trade-off:** Single-agent RAG is simpler to implement but struggles with complex, multi-step queries (e.g., matching a database record with a PDF manual).
*   **Decision:** A multi-agent graph allows separation of concerns. The planner delegates work to specialized agents that handle specific tools, resulting in cleaner outputs and simplified debugging.

### 3. Adversarial Critic Loop vs. Single-Pass Synthesis
*   **Trade-off:** A single-pass answer is faster but highly prone to hallucination.
*   **Decision:** Introducing a Critic loop forces verification. While it adds latency (~15–20 seconds per loop), it significantly decreases hallucination rates, making the engine safe for audit-heavy environments.

### 4. Local Vector Database (Qdrant) vs. Managed Cloud Vector DBs
*   **Trade-off:** Managed services handle scaling automatically but introduce data egress.
*   **Decision:** We run Qdrant locally via Docker. If the local Qdrant server is offline, the Knowledge Agent automatically falls back to an in-memory keyword overlap matrix search, guaranteeing service uptime.

---

## Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Local LLM Engine** | Ollama (Gemma / Qwen) | On-premise model serving |
| **Local Embeddings** | nomic-embed-text | Local text vectorization |
| **Vector DB** | Qdrant (Local Docker instance) | High-performance vector index |
| **Orchestration** | LangGraph | Stateful multi-agent graph compiler |
| **Persistence** | PostgreSQL Checkpointer | Session & state retention for HITL resume |
| **Backend API** | FastAPI / Uvicorn | High-throughput asynchronous routing |
| **Frontend UI** | Vanilla CSS, HTML5, JavaScript | Explorable reasoning & trace dashboard |

---

## Features

*   **100% Data Sovereignty:** Zero cloud data egress. All logs, vectors, and weights reside on your local machine.
*   **Explainable Trace UI:** A real-time visual progress tracker mapping out every stage of the agent graph as it computes.
*   **Automatic Image OCR Fallback:** Scanned image-based PDFs are automatically detected, converted to PNGs via PyMuPDF, and transcribed using local Ollama vision models.
*   **Human-In-The-Loop (HITL) Guard:** Modifying operations (SQL `DELETE`, `UPDATE`, etc.) trigger an automatic execution interrupt, prompting the user for approval before continuing.
*   **Fault-Tolerant Checkpointer:** System states are persisted using a Postgres checkpointer, allowing manual resumption of interrupted agent states even after backend restarts.

---

## Project Structure

```
PrivAgent/
├── data/
│   ├── tickets.json          # Mock Jira support issues
│   └── database.db           # SQLite internal database
├── logs/
│   └── traces.jsonl          # System observability execution logs
├── src/
│   ├── agents/
│   │   ├── security_agent.py # Input verification & sanitization
│   │   ├── intent_agent.py   # Query routing intent agent
│   │   ├── planning_agent.py # Compiles task lists
│   │   ├── db_agent.py       # SQL builder & runner
│   │   ├── docs_agent.py     # Qdrant search & document parser
│   │   ├── code_agent.py     # File system & code analysis
│   │   ├── ticket_agent.py   # Reads support tickets
│   │   ├── analyst_agent.py  # Response compiler
│   │   └── critic_agent.py   # Correctness auditor
│   ├── static/
│   │   └── index.html        # Interactive chat and graph UI
│   ├── api.py                # FastAPI routes & OCR handlers
│   ├── graph.py              # Compiled LangGraph workflow topology
│   └── state.py              # TypedDict schema defining agent state
└── README.md
```

---

## Getting Started

### 1. Prerequisites
Ensure you have Python 3.10+ and Ollama installed.

### 2. Download Local Models
Start Ollama and pull the required models:
```bash
ollama pull gemma:latest
ollama pull nomic-embed-text:latest
```

### 3. Install Dependencies
Clone the repository and install the requirements:
```bash
pip install -r requirements.txt
```

### 4. Run the Application
Start the FastAPI server:
```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000`** in your web browser.

---

## Future Improvements

1. **Local Fine-Tuning Pipeline:** Automate LoRA fine-tuning workflows on enterprise codebase structures to improve local code generation accuracy.
2. **Dynamic DAG Branching:** Support parallel fork-join branching in LangGraph, enabling the DB and Docs agents to search concurrently.
3. **Structured Guardrails:** Integrate LlamaGuard or Guardrails.ai directly into the `security_agent.py` pipeline for robust alignment verification.
4. **Agent Efficacy Evaluation:** Set up automated benchmarking tests (e.g., using Ragas or TruLens locally) to measure exact hallucination rates.

---

## Skills Demonstrated in this Project

*   **Agentic Orchestration:** Structured stateful graphs, cyclic logic, and human-in-the-loop interrupts using LangGraph.
*   **On-Premise Deployment:** Local inference configurations, model quantizations, and vector database indexing.
*   **Deterministic Evaluation:** Implementing Critic-Audit loops to mitigate LLM hallucinations.
*   **System Observability:** Building explainable tracing interfaces, structured logging, and persistent Postgres checkpointer savers.
