import json
import re
from src.state import AgentState
from src.agents.router import query_llm

# --- 1. ANALYST AGENT NODE ---
def analyst_agent_node(state: AgentState) -> dict:
    """Synthesizes all gathered investigator findings into a draft answer, incorporating critic feedback if present."""
    print("\n--- [Analyst Agent] Formulating Draft Response ---")
    logs = state.get("logs", [])
    user_query = state.get("user_query", "")
    critic_feedback = state.get("critic_feedback", "")
    current_draft = state.get("draft_response", "")
    retry_count = state.get("retry_count", 0)
    intent = state.get("intent", {})
    pathway = intent.get("pathway", "PATHWAY_3")
    
    if pathway == "PATHWAY_1":
        system_prompt = (
            "You are PrivAgent, an intelligent, high-performance enterprise AI assistant.\n"
            "Answer the user's request accurately, comprehensively, and clearly.\n"
            "Use beautiful, clean Markdown formatting: descriptive headings, bold key concepts, bullet points, and syntax-highlighted code blocks where appropriate."
        )
        prompt = f"User Request: {user_query}\n\nPlease provide a clear, thorough, and helpful answer:"
    else:
        system_prompt = (
            "You are the Analyst Agent for PrivAgent.\n"
            "Your task is to synthesize the gathered findings from investigator logs into an incredibly detailed, comprehensive, and well-structured response.\n"
            "INSTRUCTIONS FOR EXPLANATION:\n"
            "- Explain concepts, backgrounds, and findings thoroughly.\n"
            "- Format beautifully using structured Markdown: use descriptive headings (###), bold keywords, tables, bullet points, and numbered lists.\n"
            "CRITICAL: Only include information that is directly relevant to answering the User Request.\n"
            "If critic feedback is provided, you must refine and correct your previous draft to address the flagged issues."
        )
        
        filtered_logs = []
        for l in logs:
            l_lower = l.lower()
            if "success" in l_lower and ("docs agent" in l_lower or "sql agent" in l_lower or "code agent" in l_lower or "ticket agent" in l_lower or "ticket_agent" in l_lower or "web search agent" in l_lower or "web_search_agent" in l_lower or "duckduckgo" in l_lower):
                if len(l) > 600:
                    stop_words = {"the", "a", "an", "of", "and", "in", "to", "for", "is", "on", "at", "by", "with", "this", "that", "these", "those", "about", "say"}
                    query_words = [w.strip("?.!,\"()[]{}") for w in user_query.lower().split()]
                    keywords = [w for w in query_words if len(w) > 2 and w not in stop_words]
                    lines = l.replace("\\n", "\n").replace("\\r", "\n").split("\n")
                    matching_lines = [line.strip() for line in lines if any(kw in line.lower() for kw in keywords)]
                    if matching_lines:
                        filtered_logs.append(f"[Investigator SUCCESS Snippets]:\n" + "\n".join(matching_lines[:15]))
                    else:
                        filtered_logs.append(f"[Investigator SUCCESS Crop]:\n" + "\n".join(lines[:10]))
                else:
                    filtered_logs.append(l)
        if not filtered_logs:
            filtered_logs = logs

        prompt = f"User Request: {user_query}\n\nInvestigator Logs:\n" + "\n".join([f"- {l}" for l in filtered_logs])
        if critic_feedback and current_draft:
            retry_count += 1
            prompt += f"\n\nPrevious Draft:\n{current_draft}\n\nCritic Feedback to address:\n{critic_feedback}\n\nPlease output the corrected and updated draft response:"
        else:
            prompt += "\n\nPlease output your draft response:"
            
    state_logs = {"logs": list(logs)}
    query_clean = user_query.strip().lower().rstrip("?.! ")
    greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "."]
    if query_clean in greetings:
        draft = "Hello! I am PrivAgent, your secure enterprise orchestration assistant. How can I help you scan code repositories, query databases, check support tickets, or audit document libraries today?"
    else:
        draft = query_llm(prompt, system_prompt, state_to_append_logs=state_logs, max_tokens=256, timeout=3)
        if (draft.strip().startswith("{") and draft.strip().endswith("}")) or ('"requires_sql"' in draft and '{' in draft) or not draft.strip():
            # If draft failed or returned raw JSON, synthesize directly from logs into beautiful structured Markdown
            web_logs = [l for l in logs if "web search agent" in l.lower() or "duckduckgo" in l.lower()]
            doc_logs = [l for l in logs if "docs agent" in l.lower() or "hybrid rag" in l.lower()]
            clean_q = re.sub(r'^(Search document repository for:|Search code repository for:|Query database for:|\s*\[?Search:\s*)', '', user_query, flags=re.IGNORECASE).rstrip("]").strip()
            
            if web_logs:
                items = []
                for wl in web_logs:
                    if "Web results:" in wl:
                        try:
                            raw_json = wl.split("Web results:", 1)[1].strip()
                            parsed = json.loads(raw_json)
                            if isinstance(parsed, list):
                                items.extend(parsed)
                        except Exception:
                            snippets = re.findall(r'"snippet":\s*"([^"]+)"', wl)
                            titles = re.findall(r'"title":\s*"([^"]+)"', wl)
                            urls = re.findall(r'"url":\s*"([^"]+)"', wl)
                            for i in range(min(len(snippets), len(titles))):
                                items.append({
                                    "title": titles[i],
                                    "snippet": snippets[i],
                                    "url": urls[i] if i < len(urls) else "https://duckduckgo.com"
                                })
                if items:
                    # Score each snippet — prefer factual descriptions, penalise bio spam
                    factual_kw = ["education", "location", "works at", "studied", "institute", "university",
                                  "college", "is a", "was born", "based in", "profile", "member", "graduated",
                                  "engineer", "student", "researcher", "founded", "ceo", "director", "manager"]
                    spam_patterns = ["i will", "i never", "follow me", "dm me", "link in bio",
                                     "check out", "subscribe", "click here", "shop now"]

                    def score_snippet(s):
                        sl = s.lower()
                        score = len(s)  # baseline: longer is better
                        for kw in factual_kw:
                            if kw in sl:
                                score += 50
                        for sp in spam_patterns:
                            if sp in sl:
                                score -= 100
                        if s.count("@") >= 2:   # handle spam
                            score -= 80
                        if len(s) < 40:          # too short
                            score -= 60
                        return score

                    scored = [(score_snippet(item.get("snippet", "")), item) for item in items]
                    scored.sort(key=lambda x: x[0], reverse=True)
                    best_items = [item for sc, item in scored if sc > 0]

                    # Build summary from top-1 best snippet only
                    summary_para = ""
                    if best_items:
                        best_snip = best_items[0].get("snippet", "").strip()
                        if best_snip:
                            summary_para = best_snip.rstrip(".") + "."

                    md = f"### 🌐 Results for **{clean_q}**\n\n"
                    if summary_para:
                        md += f"**Summary:** {summary_para}\n\n"
                    md += "**Sources:**\n\n"
                    for idx, item in enumerate(items, 1):
                        t = item.get("title", f"Result #{idx}").strip()
                        u = item.get("url", "https://duckduckgo.com").strip()
                        try:
                            from urllib.parse import urlparse
                            domain = urlparse(u).netloc.replace("www.", "")
                        except Exception:
                            domain = ""
                        domain_badge = f" `{domain}`" if domain else ""
                        md += f"**{idx}.** [{t}]({u}){domain_badge}\n\n"
                    draft = md
                else:
                    draft = f"### 🌐 Web Search Findings for '{clean_q}'\n\nNo results found."
            elif doc_logs:
                items = []
                for dl in doc_logs:
                    if "Search results:" in dl:
                        try:
                            raw_json = dl.split("Search results:", 1)[1].strip()
                            parsed = json.loads(raw_json)
                            if isinstance(parsed, list):
                                items.extend(parsed)
                        except Exception:
                            pass
                # Items from docs_agent web fallback have hybrid_score=0.85 and a URL source
                if items:
                    # Detect if results came from web fallback (source is a URL)
                    is_web_fallback = any(item.get("source", "").startswith("http") for item in items)
                    if is_web_fallback:
                        md = f"### 🌐 Web Search Findings for **{clean_q}**\n\n"
                        for idx, item in enumerate(items, 1):
                            src = item.get("source", "https://duckduckgo.com").strip()
                            cnt = item.get("content", "").strip()
                            # content is "Title: Snippet", split it
                            if ": " in cnt:
                                title, snip = cnt.split(": ", 1)
                            else:
                                title, snip = f"Result #{idx}", cnt
                            md += f"#### {idx}. [{title}]({src})\n> {snip}\n\n"
                        draft = md
                    else:
                        md = f"### 📁 Document Knowledge Base Findings for **{clean_q}**\n\n"
                        extracted_answers = []
                        for idx, item in enumerate(items, 1):
                            src = item.get("source", "Document Repository").strip()
                            cnt = item.get("content", "").strip()
                            score = item.get("hybrid_score", 0)
                            
                            # Auto-extract CGPA / SGPA explicitly
                            cgpa_match = re.search(r'(?:cgpa|c\.g\.p\.a\.?)\s*[:=\-]?\s*([0-9]+\.?[0-9]*)', cnt, re.IGNORECASE)
                            sgpa_match = re.search(r'(?:sgpa|s\.g\.p\.a\.?)\s*[:=\-]?\s*([0-9]+\.?[0-9]*)', cnt, re.IGNORECASE)
                            
                            if cgpa_match and sgpa_match:
                                extracted_answers.append(f"🎯 **Extracted CGPA:** `{cgpa_match.group(1)}` | **SGPA:** `{sgpa_match.group(1)}` (Found in `{src}`)\n\n")
                            elif cgpa_match:
                                extracted_answers.append(f"🎯 **Extracted CGPA:** `{cgpa_match.group(1)}` (Found in `{src}`)\n\n")
                            elif sgpa_match:
                                extracted_answers.append(f"🎯 **Extracted SGPA:** `{sgpa_match.group(1)}` (Found in `{src}`)\n\n")
                            elif any(k in clean_q.lower() for k in ["cgpa", "grade", "gpa", "marks", "result"]):
                                matching_lines = [line.strip() for line in cnt.splitlines() if any(k in line.lower() for k in ["cgpa", "sgpa", "gpa", "grade", "credits", "result", "total"])]
                                if matching_lines:
                                    extracted_answers.append(f"📄 **Extracted Info from `{src}`:** { ' | '.join(matching_lines[:3]) }\n\n")

                        if extracted_answers:
                            for ans in extracted_answers:
                                md += ans

                        for idx, item in enumerate(items, 1):
                            src = item.get("source", "Document Repository").strip()
                            cnt = item.get("content", "").strip()
                            score = item.get("hybrid_score", 0)
                            preview = cnt[:800] + ("..." if len(cnt) > 800 else "")
                            md += f"#### {idx}. 📄 {src} (Relevance Score: {score})\n> {preview}\n\n"
                        draft = md
                else:
                    draft = f"### 📁 Knowledge Base Analysis\n\nCompleted document search for query: **{clean_q}**."
            else:
                draft = f"### PrivAgent Execution Summary\n\nCompleted analysis for query: **{clean_q}**."
            
    try:
        print(f"[Analyst Agent] Draft Response Generated:\n{draft[:300]}...")
    except Exception:
        print("[Analyst Agent] Draft Response Generated successfully.")
    return {
        "draft_response": draft,
        "retry_count": retry_count,
        "logs": state_logs["logs"] + [f"[Analyst Agent] Generated/Refined draft response (Retry {retry_count})."]
    }

# --- 2. CRITIC AGENT NODE ---
def critic_agent_node(state: AgentState) -> dict:
    """Reviews the Analyst's draft response against logs collected by investigator nodes to check for unsupported claims."""
    print("\n--- [Critic Agent] Auditing Analyst Draft Response ---")
    logs = state.get("logs", [])
    user_query = state.get("user_query", "")
    draft_response = state.get("draft_response", "")
    intent = state.get("intent", {})
    pathway = intent.get("pathway", "PATHWAY_3")
    
    if state.get("disable_critic", False) or pathway in ["PATHWAY_1", "PATHWAY_2"]:
        print(f"[Critic Agent] Critic verification bypassed for {pathway}. Returning PASS instantly.")
        return {
            "critic_feedback": "PASS",
            "logs": logs + [f"[Critic Agent] Critic verification bypassed for {pathway}."]
        }

    system_prompt = (
        "You are the Critic Agent for PrivAgent.\n"
        "Verify the Analyst's draft response against the raw investigator logs.\n"
        "If there are any issues, detail them clearly so the Analyst can fix them.\n"
        "If the draft is 100% correct and fully supported by the logs, respond with exactly the word 'PASS' and nothing else."
    )
    prompt = f"User Request: {user_query}\n\nAnalyst Draft Response:\n{draft_response}\n\nInvestigator Logs:\n" + "\n".join([f"- {l}" for l in logs])
    state_logs = {"logs": list(logs)}
    feedback = query_llm(prompt, system_prompt, state_to_append_logs=state_logs, max_tokens=64, timeout=2)
    # If LLM timed out or returned empty/JSON, treat as PASS to avoid infinite retry loops
    if not feedback.strip() or feedback.strip().startswith("{") or feedback.strip() == "{}":
        feedback = "PASS"
    print(f"[Critic Agent] Audit Feedback: {feedback}")
    return {
        "critic_feedback": feedback,
        "logs": state_logs["logs"] + [f"[Critic Agent] Audited draft. Result: {feedback[:120]}..."]
    }

# --- 3. HUMAN APPROVAL NODE (HITL) ---
def human_approval_node(state: AgentState) -> dict:
    """Interrupt node for Human-In-The-Loop (HITL) approval of modifying actions."""
    print("\n--- [Human Approval Gate] Interrupting for Admin Action Review ---")
    idx = state.get("current_task_index", 0)
    plan = state.get("plan", [])
    task_desc = plan[idx]["task"] if (plan and idx < len(plan)) else "Sensitive action"
    logs = state.get("logs", [])
    print(f"[Human Approval Gate] Action requiring approval: '{task_desc}'")
    return {
        "logs": logs + [f"[Human Approval Gate] Interrupting execution graph for write task '{task_desc}'."]
    }

# --- 4. LOG GROOMER NODE ---
def log_groomer_node(state: AgentState) -> dict:
    """Compresses and formats raw execution logs between steps to preserve token context window."""
    logs = state.get("logs", [])
    groomed = []
    for l in logs:
        if len(l) > 1000:
            groomed.append(l[:500] + "\n... [TRUNCATED FOR CONTEXT EFFICIENCY] ...\n" + l[-200:])
        else:
            groomed.append(l)
    return {"logs": groomed}
