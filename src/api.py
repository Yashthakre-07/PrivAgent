import os
import time
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from src.graph import get_graph
from src.logger import log_trace

app = FastAPI(title="PrivAgent Orchestration Portal")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extracts text content from a PDF file. 
    It first attempts standard text extraction. If the PDF has no selectable text 
    (e.g., scanned document), it falls back to page-by-page vision OCR using 
    a local Ollama vision model.
    """
    import io
    import pypdf
    
    # --- Step 1: Standard Text Extraction ---
    try:
        # Load PDF bytes into an in-memory stream
        pdf_file = io.BytesIO(file_bytes)
        reader = pypdf.PdfReader(pdf_file)
        text_parts = []
        
        # Loop through pages and extract textual metadata
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
                
        # Join extracted text and return if successful
        result = "\n".join(text_parts).strip()
        if result:
            return result
    except Exception as e:
        print(f"[API] pypdf extraction failed: {e}")
    
    # --- Step 2: Fallback Vision-based OCR via Ollama ---
    print("[API] Text extraction empty, attempting vision OCR via Ollama...")
    try:
        import fitz  # PyMuPDF
        import base64
        import json
        import urllib.request
        
        # Re-open the PDF using PyMuPDF from bytes
        pdf_file = io.BytesIO(file_bytes)
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        full_text = []
        
        # Render each page to an image and run OCR
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Render page at 150 DPI for optimal text legibility and image size
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            
            # Construct API payload for the multimodal Ollama vision model
            payload = {
                "model": "gemma4:latest",
                "prompt": "You are an OCR assistant. Carefully read and transcribe ALL the text you see in this image exactly as it appears. Include every word, number, date, name, and label. Do not skip any content.",
                "images": [img_b64],
                "stream": False
            }
            
            # Make a POST request to Ollama's local generation endpoint
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            
            try:
                # Execute request with a 120s timeout
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    page_text = data.get("response", "").strip()
                    if page_text:
                        # Append the OCR results for the page
                        full_text.append(f"[Page {page_num + 1}]\n{page_text}")
            except Exception as e:
                print(f"[API] Vision OCR failed for page {page_num}: {e}")
        
        # Combine all OCR page transcriptions
        result = "\n\n".join(full_text).strip()
        if result:
            print(f"[API] Vision OCR succeeded: {len(result)} chars extracted.")
            return result
    except Exception as e:
        print(f"[API] Vision OCR fallback failed: {e}")
    
    return ""



# --- API Endpoint: Available Models ---
@app.get("/api/models")
def get_available_models():
    """
    Queries local Ollama tags API and returns all installed LLM models available for selection.
    """
    import urllib.request
    import json
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            models = [
                m["name"] for m in data.get("models", [])
                if "embed" not in m["name"].lower()
            ]
            if models:
                return {"models": models}
    except Exception as e:
        print(f"[API] Error fetching models from Ollama: {e}")
    return {"models": ["gemma4:latest", "qwen3:8b", "qwen3:0.6b"]}


# --- API Endpoint: File Upload ---
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Handles PDF or text file uploads.
    Extracts text contents (using standard/OCR methods for PDF or utf-8 decoding for other formats)
    and updates the Docs Agent's local document database context dynamically.
    """
    try:
        # Read raw uploaded file bytes
        content_bytes = await file.read()
        
        # Determine extraction strategy based on file extension
        filename_lower = file.filename.lower()
        if filename_lower.endswith(".pdf"):
            # Attempt normal extraction first, then fall back to OCR via local vision model
            content = extract_text_from_pdf(content_bytes)
            if not content.strip():
                raise HTTPException(status_code=400, detail="This PDF appears to be a scanned image with no readable text. Vision OCR was attempted but could not extract any content. Please try a text-based PDF.")
        else:
            # Decode text files (txt, md, log, csv, etc.) ignoring decoding errors
            content = content_bytes.decode("utf-8", errors="ignore")
        
        # Dynamically append/overwrite this document in Docs Agent memory and vector DB
        from src.agents.investigators import add_document_to_context
        add_document_to_context(content, file.filename)
        
        return {
            "status": "success",
            "filename": file.filename,
            "char_count": len(content)
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Data Transfer Objects (Pydantic Models) ---
from typing import Optional

class QueryRequest(BaseModel):
    """Payload format expected for incoming orchestration portal user queries."""
    query: str
    role: str
    model: Optional[str] = None

class ApproveRequest(BaseModel):
    """Payload format expected when approving or rejecting a task waiting for human input."""
    thread_id: str
    approved: bool


import threading

# Global registry to track currently active LangGraph execution background threads
ACTIVE_THREADS = set()


# --- Background Executors for LangGraph Checkpointing ---

def run_graph_background(thread_id: str, inputs: dict, config: dict):
    """
    Spins up and streams the LangGraph orchestrator steps from scratch in the background.
    Logs execution times and node outcomes to trace logs. Pauses if a human feedback node is hit.
    """
    try:
        # Load the compiled state graph
        graph = get_graph()
        start_time = time.time()
        
        # Stream graph node execution events sequentially
        for event in graph.stream(inputs, config=config):
            for node_name, state_values in event.items():
                # Measure latency of the individual node
                latency = (time.time() - start_time) * 1000
                log_trace(thread_id, node_name, f"Successfully executed node.", latency_ms=latency)
                start_time = time.time()
            
            # Stop streaming if the next state transitions to a manual human approval node
            state = graph.get_state(config)
            if state.next and "human_approval" in state.next:
                break
    except Exception as e:
        log_trace(thread_id, "API", f"Background execution error: {e}", level="ERROR")
    finally:
        # Thread cleanup
        ACTIVE_THREADS.discard(thread_id)


def resume_graph_background(thread_id: str, config: dict):
    """
    Resumes an already paused LangGraph execution from its checkpoint in the background.
    Used after a human has approved/rejected a planned step.
    """
    try:
        # Load the compiled state graph
        graph = get_graph()
        start_time = time.time()
        
        # Resume streaming (passing None to state continues execution from checkpointer)
        for event in graph.stream(None, config=config):
            for node_name, state_values in event.items():
                # Measure and log node latency
                latency = (time.time() - start_time) * 1000
                log_trace(thread_id, node_name, f"Resumed and executed node successfully.", latency_ms=latency)
                start_time = time.time()
            
            # Check if execution paused again due to another human approval requirement
            state = graph.get_state(config)
            if state.next and "human_approval" in state.next:
                break
    except Exception as e:
        log_trace(thread_id, "API", f"Background resume error: {e}", level="ERROR")
    finally:
        # Thread cleanup
        ACTIVE_THREADS.discard(thread_id)


# --- API Endpoint: Trigger Query ---
@app.post("/api/query")
def run_query(req: QueryRequest):
    """
    Initializes a new LangGraph thread, sets initial inputs, and executes the orchestrator 
    asynchronous background thread to prevent HTTP timeouts.
    """
    thread_id = f"web_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "user_query": req.query,
        "user_role": req.role,
        "approved": False,
        "selected_model": req.model
    }
    
    log_trace(thread_id, "API", f"Received query request for role '{req.role}': '{req.query}'")
    
    # Track the active background thread
    ACTIVE_THREADS.add(thread_id)
    
    # Spin up background thread for graph execution
    t = threading.Thread(target=run_graph_background, args=(thread_id, inputs, config))
    t.daemon = True
    t.start()
    
    return {
        "status": "running",
        "thread_id": thread_id
    }


# --- API Endpoint: Approve Task Step ---
@app.post("/api/approve")
def approve_query(req: ApproveRequest):
    """
    Updates the paused state of an existing LangGraph thread with human approval (True/False)
    and triggers the background resumption runner.
    """
    config = {"configurable": {"thread_id": req.thread_id}}
    graph = get_graph()
    
    log_trace(req.thread_id, "API", f"Received manual approval: {req.approved}")
    
    try:
        # Inject the human approval result directly into the checkpointed graph state
        graph.update_state(config, {"approved": req.approved}, as_node="human_approval")
        
        # Track the active background thread
        ACTIVE_THREADS.add(req.thread_id)
        
        # Spin up background thread to resume the paused graph
        t = threading.Thread(target=resume_graph_background, args=(req.thread_id, config))
        t.daemon = True
        t.start()
        
        return {
            "status": "running",
            "thread_id": req.thread_id
        }
    except Exception as e:
        log_trace(req.thread_id, "API", f"Error during resume approval initiation: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))


# --- API Endpoint: Get Execution Status ---
@app.get("/api/status/{thread_id}")
def get_status(thread_id: str):
    """
    Retrieves the current execution status, logs, current plan, active step indices, 
    and final response for a given LangGraph thread ID.
    """
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    state = graph.get_state(config)
    
    # Handle checkpointer status before state values are fully populated
    if not state.values:
        if thread_id in ACTIVE_THREADS:
            return {
                "status": "running",
                "thread_id": thread_id,
                "final_response": "",
                "task_desc": "",
                "logs": ["[Portal API] Initializing agent graph checkpointer..."]
            }
        raise HTTPException(status_code=404, detail="Thread not found.")
        
    status = "running"
    task_desc = ""
    final_resp = state.values.get("final_response", "") or state.values.get("draft_response", "")
    
    # Analyze state to determine current status
    if state.next:
        if "human_approval" in state.next:
            status = "interrupted"  # Paused, waiting for human feedback
            plan = state.values.get("plan", [])
            idx = state.values.get("current_task_index", 0)
            if idx < len(plan):
                task_desc = plan[idx]["task"]
        elif final_resp:
            status = "completed"
    elif final_resp or not state.next:
        status = "completed"  # Successfully finished
        
    intent = state.values.get("intent", {})
    pathway = intent.get("pathway", "PATHWAY_3")
    target_agent = intent.get("target_agent")

    return {
        "status": status,
        "thread_id": thread_id,
        "final_response": final_resp,
        "task_desc": task_desc,
        "logs": state.values.get("logs", []),
        "plan": state.values.get("plan", []),
        "current_task_index": state.values.get("current_task_index", 0),
        "pathway": pathway,
        "target_agent": target_agent
    }


# --- API Endpoint: Get State History ---
@app.get("/api/history/{thread_id}")
def get_history(thread_id: str):
    """Retrieves raw state values and next node transitions for debugging thread history."""
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    state = graph.get_state(config)
    if not state.values:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return {
        "values": state.values,
        "next": state.next
    }


# --- Web Page Serving and Static Files ---
@app.get("/")
def get_index():
    """Serves the main entry portal frontend HTML file."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Mount the static directory to serve resources like CSS and JS files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

