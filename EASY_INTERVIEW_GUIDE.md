# PrivAgent: Simple, Plain-English Interview Guide
**Author:** Yash Thakre (Roll No: 23BTB0A33 | NIT Warangal)

---

## 🌟 1. The Core Idea in Simple Words

### What is PrivAgent? (The Restaurant Analogy)
Imagine a busy restaurant:
- **Standard AI (like ChatGPT):** Like asking one waiter who tries to cook, clean, serve, and do the billing all by himself. He gets tired, forgets things, and sometimes makes up orders (hallucinates).
- **PrivAgent:** Like an **entire well-managed restaurant team**:
  1. **Security Guard (`Security Agent`)**: Checks ID at the door and stops bad actors.
  2. **Receptionist (`Intent Agent`)**: Greets you and decides what you need.
  3. **Manager (`Planning Agent`)**: Breaks your big request into smaller tasks for the team.
  4. **Specialist Chefs (`Investigator Agents`)**: 
     - **Database Chef**: Gets data from SQL tables.
     - **Docs Chef**: Reads internal PDF files and manuals.
     - **Code Chef**: Checks python code and GitHub files.
     - **Ticket Chef**: Checks customer support tickets in Jira.
  5. **Head Chef / Writer (`Analyst Agent`)**: Collects all ingredients and prepares the final dish/report.
  6. **Quality Inspector (`Critic Agent`)**: Tastes and checks every plate before it goes to the customer. If anything is wrong, sends it back to fix!
  7. **Owner Approval (`Human-In-The-Loop`)**: If something involves spending money or deleting data, the manager asks the human owner for permission first.

---

## 🚀 2. How to Introduce Your Project (Say This Out Loud)

> *"Hi! For my project, I built **PrivAgent**—a Private Enterprise AI Operating System.*  
> 
> *The problem is that companies have lots of private data (in SQL databases, PDFs, Jira tickets, and code repositories). They cannot upload this data to public ChatGPT because of privacy laws and data leak risks.*  
> 
> *I used **LangGraph** to build a team of specialized AI agents running securely on local hardware. When a user asks a complex question, the system plans tasks, sends them to specialized agents (SQL, Docs RAG, Code, Tickets), verifies the answer through a Critic to stop hallucinations, and gives a 100% accurate, private answer.*  
> 
> *I also added **Semantic Kernel** to route 90% of requests to free local models and only use cloud **Azure OpenAI** when needed, cutting costs by 90%."*

---

## 📂 3. File-by-File Walkthrough (What Each File Does)

| File Name | What It Does (Simple English) |
| :--- | :--- |
| **`src/state.py`** | The **Shared Notebook**. It holds all data (user question, plan, logs, draft answer, retry count) that agents pass to each other. |
| **`src/graph.py`** | The **Traffic Controller**. It connects all the agent nodes together in a loop using LangGraph and decides who goes next. |
| **`src/agents/router.py`** | Contains 3 gateway agents: **Security Agent** (checks permissions), **Intent Agent** (decides which tools are needed), and **Planning Agent** (creates the step-by-step task plan). |
| **`src/agents/investigators.py`** | Contains the **Worker Agents**: `sql_agent` (queries database), `docs_agent` (searches PDFs), `code_agent` (scans code), `ticket_agent` (finds Jira tickets), and `web_search_agent` (DuckDuckGo search). |
| **`src/agents/synthesizer.py`** | Contains the **Finishing Agents**: `analyst_agent` (writes the draft summary), `critic_agent` (catches hallucinations), and `human_approval` (asks admin before modifying data). |
| **`src/sk_router.py`** | The **Cost Saver Gateway**. Sends queries to local Ollama first for $0 cost. If local fails, calls Azure OpenAI `gpt-4o`. |
| **`src/mcp_tools.py`** | The **Standard Tool Adapter**. Wraps all agent actions using standard Model Context Protocol (MCP) so tools can be easily reused. |
| **`src/api.py`** | The **Web Server**. Uses FastAPI to connect the user interface to our Python multi-agent graph and handles PDF uploads. |
| **`evaluate.py`** | The **Test Benchmark**. Runs 16 automated tests to prove that our Critic agent actually improves accuracy and stops fake answers. |

---

## 🔍 4. Key Features Explained Simply

### 1. What is "Hybrid RAG"? (Dense Vector + BM25)
- **Problem:** Normal vector search is great for general concepts, but terrible at exact keywords like roll numbers (`23BTB0A33`), port numbers (`5432`), or error codes (`JIRA-409`).
- **Solution:** We combine two searches:
  1. **Dense Vector (Qdrant)**: Understands meaning and synonyms (70% weight).
  2. **Sparse BM25**: Finds exact word matches (30% weight).
- **Result:** You never miss exact numbers, names, or general meanings!

### 2. How does the "Critic Agent" stop hallucinations?
- When the Analyst writes a summary, the **Critic Agent** reads the raw logs from the investigator agents line-by-line.
- If the Analyst wrote something that wasn't in the raw data (like making up a phone number), the Critic rejects it and makes the Analyst rewrite it correctly.

### 3. How do we save 90% on Cloud Costs?
- Cloud AI APIs (like GPT-4) charge money for every word sent.
- We run open-source models (like Qwen-2.5 or Gemma) on our own computer/server using **Ollama for FREE**.
- 90 out of 100 queries are solved locally for $0.
- Only the 10 heavy or failed queries are sent to **Azure OpenAI**, saving 90% of the bill!

### 4. What is "Human-in-the-Loop" (HITL)?
- If a user asks to `DELETE` a database record or `UPDATE` a customer file, the system pauses execution.
- It displays a prompt to the admin: *"Do you approve this delete action?"*
- It only runs the delete command after the human clicks **Approve**.

---

## 🎯 5. Top 5 Interview Questions & Easy Answers

### Q1: "Why did you use LangGraph instead of standard LangChain?"
> *"Standard LangChain only works in a straight line from Step A to B to C. If Step B fails, the whole program crashes.  
> With **LangGraph**, I can create loops! If the Critic finds a mistake, it loops back to the Analyst. If an investigator agent fails, the Planner creates a new plan. Plus, LangGraph supports saving state in PostgreSQL and pausing for human approval."*

### Q2: "What is Model Context Protocol (MCP)?"
> *"MCP is an open standard created by Anthropic that acts like a universal USB plug for AI. Instead of writing custom messy code for each database or API, MCP gives a standard format (JSON-RPC) so any agent can connect to any tool cleanly."*

### Q3: "What happens if a user tries to run a malicious SQL command like DROP TABLE?"
> *"Our **Security Agent** checks the user's role before any tool runs. If a regular user sends `DROP TABLE` or `sudo`, the Security Agent blocks it instantly with a `[SECURITY BLOCK]` and stops the entire graph before anything touches the database."*

### Q4: "How does the system handle scanned PDF files?"
> *"First, it tries normal text extraction using `pypdf`. If the PDF is a scanned image with 0 selectable text, it renders the page into an image using `PyMuPDF (fitz)` and uses a local vision model to do OCR and read every word automatically."*

### Q5: "What were the biggest challenges you faced?"
> *"1. **Small models misclassifying tasks**: Smaller local models sometimes sent code tasks to the SQL agent. I fixed this by adding a rule-based Plan Validator.  
> 2. **Context window getting full**: Multi-agent logs got too long, so I created a `log_groomer` to compress logs between steps.  
> 3. **Stopping fake information**: Generative models made up missing details, which I solved by building the Critic auditing loop."*

---

## 💡 Quick Tips for Interview Day:
1. **Be relaxed and confident:** You built this whole system from state definitions to evaluation benchmarks.
2. **Use the Restaurant / Team analogy:** Interviewers love candidates who can explain complex tech in simple, clean terms.
3. **Highlight your numbers:** Mention the **90% cost savings**, **100% citation precision**, and **81.25% routing accuracy**.
