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
    import io
    import pypdf
    # First try standard text extraction
    try:
        pdf_file = io.BytesIO(file_bytes)
        reader = pypdf.PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        result = "\n".join(text_parts).strip()
        if result:
            return result
    except Exception as e:
        print(f"[API] pypdf extraction failed: {e}")
    
    # Fallback: use PyMuPDF to render pages as images then OCR via Ollama vision
    print("[API] Text extraction empty, attempting vision OCR via Ollama...")
    try:
        import fitz
        import base64
        import json
        import urllib.request
        
        pdf_file = io.BytesIO(file_bytes)
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        full_text = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Render at 150 DPI for good OCR quality
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            
            payload = {
                "model": "gemma4:latest",
                "prompt": "You are an OCR assistant. Carefully read and transcribe ALL the text you see in this image exactly as it appears. Include every word, number, date, name, and label. Do not skip any content.",
                "images": [img_b64],
                "stream": False
            }
            
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            
            try:
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    page_text = data.get("response", "").strip()
                    if page_text:
                        full_text.append(f"[Page {page_num + 1}]\n{page_text}")
            except Exception as e:
                print(f"[API] Vision OCR failed for page {page_num}: {e}")
        
        result = "\n\n".join(full_text).strip()
        if result:
            print(f"[API] Vision OCR succeeded: {len(result)} chars extracted.")
            return result
    except Exception as e:
        print(f"[API] Vision OCR fallback failed: {e}")
    
    return ""


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        content_bytes = await file.read()
        
        # Parse based on file type
        filename_lower = file.filename.lower()
        if filename_lower.endswith(".pdf"):
            content = extract_text_from_pdf(content_bytes)
            if not content.strip():
                raise HTTPException(status_code=400, detail="This PDF appears to be a scanned image with no readable text. Vision OCR was attempted but could not extract any content. Please try a text-based PDF.")
        else:
            # Fallback to standard text decoding (txt, md, log, csv, etc.)
            content = content_bytes.decode("utf-8", errors="ignore")
        
        # Add to Docs Agent memory context
        from src.agents.docs_agent import add_document_to_context
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

from typing import Optional

class QueryRequest(BaseModel):
    query: str
    role: str
    model: Optional[str] = None

class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool

import threading

ACTIVE_THREADS = set()

def run_graph_background(thread_id: str, inputs: dict, config: dict):
    try:
        graph = get_graph()
        start_time = time.time()
        for event in graph.stream(inputs, config=config):
            for node_name, state_values in event.items():
                latency = (time.time() - start_time) * 1000
                log_trace(thread_id, node_name, f"Successfully executed node.", latency_ms=latency)
                start_time = time.time()
            
            # Check if interrupted
            state = graph.get_state(config)
            if state.next and "human_approval" in state.next:
                break
    except Exception as e:
        log_trace(thread_id, "API", f"Background execution error: {e}", level="ERROR")
    finally:
        ACTIVE_THREADS.discard(thread_id)

def resume_graph_background(thread_id: str, config: dict):
    try:
        graph = get_graph()
        start_time = time.time()
        for event in graph.stream(None, config=config):
            for node_name, state_values in event.items():
                latency = (time.time() - start_time) * 1000
                log_trace(thread_id, node_name, f"Resumed and executed node successfully.", latency_ms=latency)
                start_time = time.time()
            
            # Check if interrupted
            state = graph.get_state(config)
            if state.next and "human_approval" in state.next:
                break
    except Exception as e:
        log_trace(thread_id, "API", f"Background resume error: {e}", level="ERROR")
    finally:
        ACTIVE_THREADS.discard(thread_id)

@app.post("/api/query")
def run_query(req: QueryRequest):
    thread_id = f"web_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "user_query": req.query,
        "user_role": req.role,
        "approved": False,
        "selected_model": req.model
    }
    
    log_trace(thread_id, "API", f"Received query request for role '{req.role}': '{req.query}'")
    
    # Register thread as active
    ACTIVE_THREADS.add(thread_id)
    
    # Start graph execution in background thread
    t = threading.Thread(target=run_graph_background, args=(thread_id, inputs, config))
    t.daemon = True
    t.start()
    
    return {
        "status": "running",
        "thread_id": thread_id
    }

@app.post("/api/approve")
def approve_query(req: ApproveRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    graph = get_graph()
    
    log_trace(req.thread_id, "API", f"Received manual approval: {req.approved}")
    
    try:
        # Update state with the manual approval outcome
        graph.update_state(config, {"approved": req.approved}, as_node="human_approval")
        
        # Register thread as active
        ACTIVE_THREADS.add(req.thread_id)
        
        # Start graph resumption in background thread
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

@app.get("/api/status/{thread_id}")
def get_status(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    state = graph.get_state(config)
    
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
    final_resp = state.values.get("final_response", "")
    
    # Determine the status
    if state.next:
        if "human_approval" in state.next:
            status = "interrupted"
            plan = state.values.get("plan", [])
            idx = state.values.get("current_task_index", 0)
            if idx < len(plan):
                task_desc = plan[idx]["task"]
    elif final_resp:
        status = "completed"
        
    return {
        "status": status,
        "thread_id": thread_id,
        "final_response": final_resp,
        "task_desc": task_desc,
        "logs": state.values.get("logs", []),
        "plan": state.values.get("plan", []),
        "current_task_index": state.values.get("current_task_index", 0)
    }

@app.get("/api/history/{thread_id}")
def get_history(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    state = graph.get_state(config)
    if not state.values:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return {
        "values": state.values,
        "next": state.next
    }

@app.get("/")
def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
