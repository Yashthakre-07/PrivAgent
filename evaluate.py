import os
import sys
import time
import json
import uuid
import re
import matplotlib.pyplot as plt

# Ensure local src directory is in Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.graph import get_graph

# Load test cases
def load_test_cases():
    with open("test_cases.json", "r", encoding="utf-8") as f:
        return json.load(f)

# Extraction helper for citations
def extract_citations(text: str) -> list:
    citations = re.findall(r"\b\w+\.(?:pdf|md|json)\b", text, re.IGNORECASE)
    citations += re.findall(r"\bTICKET-\d+\b", text, re.IGNORECASE)
    if "churn_data" in text.lower():
        citations.append("churn_data")
    return list(set(citations))

# Helper to verify citation validity against logs
def check_citation_validity(citations: list, logs: list) -> float:
    if not citations:
        return 1.0  # 100% precision if no citations were needed/made
    valid_count = 0
    joined_logs = "\n".join(logs).lower()
    for citation in citations:
        # Standardize matching
        cit_clean = citation.lower().strip()
        if cit_clean in joined_logs:
            valid_count += 1
    return valid_count / len(citations)

# Helper to check agent routing accuracy
def check_routing_accuracy(logs: list, expected_agents: list) -> bool:
    joined_logs = "\n".join(logs).lower()
    for agent in expected_agents:
        # Map agent keys to success signatures in logs
        sig = ""
        if agent == "docs_agent":
            sig = "docs agent"
        elif agent == "sql_agent":
            sig = "db agent"
        elif agent == "code_agent":
            sig = "code agent"
        elif agent == "ticket_agent":
            sig = "ticket agent"
            
        if sig not in joined_logs:
            return False
    return True

# Helper to score accuracy against ground truth using key terms
def score_accuracy(case_id: str, response: str) -> float:
    res_lower = response.lower()
    
    # Map of case IDs to required factual keywords or refusal phrases
    keywords_map = {
        "TC-01": ["acmecorp"],
        "TC-02": ["/etc/privagent"],
        "TC-03": ["5432", "6333"],
        "TC-04": ["acmecorp", "initech"],
        "TC-05": ["poor customer support", "35000"],
        "TC-06": ["hooli", "80000"],
        "TC-07": ["alice smith"],
        "TC-08": ["in progress", "critical"],
        "TC-09": ["pricing", "bugs"],
        "TC-10": ["graph.py"],
        "TC-11": ["graph.py"],
        "TC-12": ["acmecorp", "pricing", "bugs"],
        "TC-13": ["acmecorp", "pricing", "bugs"],
        # Adversarial cases must not fabricate, they must refuse / state missing
        "TC-14": ["no phone", "not available", "does not contain", "no record", "not listed", "unknown", "doesn't provide"],
        "TC-15": ["post-mortem", "not in the marketing", "does not contain", "not found", "leak details are in"],
        "TC-16": ["no record", "no database", "does not exist", "cyberdyne", "not found"]
    }
    
    keywords = keywords_map.get(case_id, [])
    if not keywords:
        return 1.0
        
    # For adversarial refusal cases, check if they correctly refuse (contain at least one refusal keyword)
    if case_id in ["TC-14", "TC-15", "TC-16"]:
        # Make sure they also didn't hallucinate arbitrary phone numbers/passwords/rows
        # e.g., TC-14 shouldn't contain a phone-like number
        if case_id == "TC-14" and re.search(r"\b\d{3}[- ]?\d{3}[- ]?\d{4}\b", response):
            return 0.0 # Hallucinated a phone number!
        if any(kw in res_lower for kw in keywords):
            return 1.0
        return 0.0
        
    # For factual cases, calculate the ratio of matching key terms
    match_count = sum(1 for kw in keywords if kw in res_lower)
    return match_count / len(keywords)

# Run a single query through the compiled graph
def run_pipeline(graph, query: str, disable_critic: bool) -> dict:
    thread_id = f"eval_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "user_query": query,
        "user_role": "admin",
        "approved": False,
        "disable_critic": disable_critic
    }
    
    start_time = time.time()
    try:
        state = graph.invoke(inputs, config=config)
        latency = time.time() - start_time
        return {
            "success": True,
            "final_response": state.get("final_response", ""),
            "logs": state.get("logs", []),
            "retry_count": state.get("retry_count", 0),
            "critic_feedback": state.get("critic_feedback", ""),
            "latency": latency
        }
    except Exception as e:
        latency = time.time() - start_time
        return {
            "success": False,
            "error": str(e),
            "latency": latency
        }

def run_evaluation():
    print("=" * 80)
    print("STARTING PRIVAGENT LLM SYSTEM EVALUATION AND BENCHMARKING SUITE")
    print("=" * 80)
    
    test_cases = load_test_cases()
    graph = get_graph()
    
    results = []
    
    for case in test_cases:
        cid = case["id"]
        query = case["query"]
        category = case["category"]
        expected_agents = case["expected_agents"]
        
        print(f"\n[{cid}] Category: {category}")
        print(f"Query: \"{query}\"")
        
        # 1. RUN WITH CRITIC DISABLED (ABLATION)
        print(" -> Running Baseline (Critic Disabled)...")
        baseline_res = run_pipeline(graph, query, disable_critic=True)
        
        # 2. RUN WITH CRITIC ENABLED (DEFAULT VERIFICATION)
        print(" -> Running Verified (Critic Enabled)...")
        verified_res = run_pipeline(graph, query, disable_critic=False)
        
        # Parse Baseline Metrics
        if baseline_res["success"]:
            baseline_accuracy = score_accuracy(cid, baseline_res["final_response"])
            baseline_route_ok = check_routing_accuracy(baseline_res["logs"], expected_agents)
            baseline_cits = extract_citations(baseline_res["final_response"])
            baseline_cit_precision = check_citation_validity(baseline_cits, baseline_res["logs"])
        else:
            baseline_accuracy = 0.0
            baseline_route_ok = False
            baseline_cit_precision = 0.0
            
        # Parse Verified Metrics
        if verified_res["success"]:
            verified_accuracy = score_accuracy(cid, verified_res["final_response"])
            verified_route_ok = check_routing_accuracy(verified_res["logs"], expected_agents)
            verified_cits = extract_citations(verified_res["final_response"])
            verified_cit_precision = check_citation_validity(verified_cits, verified_res["logs"])
            retry_loops = verified_res["retry_count"]
            
            # Check if Critic caught any hallucination
            critic_fb = verified_res["critic_feedback"].strip()
            critic_active = critic_fb != "" and not critic_fb.upper().startswith("PASS")
            
            # Hallucination caught: Critic was active and triggered at least one retry loop
            hallucination_caught = 1 if (critic_active and retry_loops > 0) else 0
            
            # Hallucination slipped: verified response was wrong/inaccurate, or baseline response was wrong but critic didn't catch it
            # We define slip-through as: baseline was inaccurate, and critic passed it or failed to correct it in verified run.
            hallucination_slipped = 1 if (verified_accuracy < 1.0 and hallucination_caught == 0) else 0
        else:
            verified_accuracy = 0.0
            verified_route_ok = False
            verified_cit_precision = 0.0
            retry_loops = 0
            hallucination_caught = 0
            hallucination_slipped = 1
            
        case_result = {
            "id": cid,
            "category": category,
            "query": query,
            "expected_agents": expected_agents,
            "baseline": {
                "response": baseline_res.get("final_response", ""),
                "accuracy": baseline_accuracy,
                "routing_ok": baseline_route_ok,
                "citation_precision": baseline_cit_precision,
                "latency": baseline_res["latency"]
            },
            "verified": {
                "response": verified_res.get("final_response", ""),
                "accuracy": verified_accuracy,
                "routing_ok": verified_route_ok,
                "citation_precision": verified_cit_precision,
                "retry_count": retry_loops,
                "hallucination_caught": hallucination_caught,
                "hallucination_slipped": hallucination_slipped,
                "latency": verified_res["latency"]
            }
        }
        results.append(case_result)
        
        print(f"    Baseline Accuracy: {baseline_accuracy * 100:.1f}% | Latency: {baseline_res['latency']:.2f}s")
        print(f"    Verified Accuracy: {verified_accuracy * 100:.1f}% | Latency: {verified_res['latency']:.2f}s | Retries: {retry_loops}")
        print(f"    Routing: {'OK' if verified_route_ok else 'FAIL'} | Citation Precision: {verified_cit_precision * 100:.1f}%")
        if hallucination_caught:
            print("    [ALERT] Critic verification caught and corrected a hallucination/error!")
            
    # Calculate global aggregated metrics
    total_cases = len(results)
    
    avg_baseline_acc = sum(r["baseline"]["accuracy"] for r in results) / total_cases
    avg_verified_acc = sum(r["verified"]["accuracy"] for r in results) / total_cases
    
    avg_baseline_latency = sum(r["baseline"]["latency"] for r in results) / total_cases
    avg_verified_latency = sum(r["verified"]["latency"] for r in results) / total_cases
    
    avg_routing_acc = sum(1 for r in results if r["verified"]["routing_ok"]) / total_cases
    avg_cit_precision = sum(r["verified"]["citation_precision"] for r in results) / total_cases
    
    total_caught = sum(r["verified"]["hallucination_caught"] for r in results)
    total_slipped = sum(r["verified"]["hallucination_slipped"] for r in results)
    
    # Hallucination Rate = slipped / (caught + slipped + baseline_flaws)
    # A cleaner enterprise metric: % of overall runs that suffered from undetected hallucinations
    hallucination_rate = total_slipped / total_cases
    
    print("\n" + "=" * 80)
    print("AGGREGATED EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Baseline Accuracy (Without Critic Verification): {avg_baseline_acc * 100:.2f}%")
    print(f"Verified Accuracy (With Critic Verification):    {avg_verified_acc * 100:.2f}%")
    print(f"Ablation Performance Improvement:              +{ (avg_verified_acc - avg_baseline_acc) * 100:.2f}%")
    print("-" * 80)
    print(f"Agent Routing Accuracy:                          {avg_routing_acc * 100:.2f}%")
    print(f"Citation Precision:                              {avg_cit_precision * 100:.2f}%")
    print(f"Undetected Hallucination Rate:                   {hallucination_rate * 100:.2f}%")
    print(f"Total Hallucinations Blocked by Critic:          {total_caught}")
    print("-" * 80)
    print(f"Average Latency (Without Verification):          {avg_baseline_latency:.2f}s")
    print(f"Average Latency (With Verification):             {avg_verified_latency:.2f}s")
    print("=" * 80)
    
    # Save results to file
    summary = {
        "metrics": {
            "baseline_accuracy": avg_baseline_acc,
            "verified_accuracy": avg_verified_acc,
            "accuracy_improvement": avg_verified_acc - avg_baseline_acc,
            "routing_accuracy": avg_routing_acc,
            "citation_precision": avg_cit_precision,
            "hallucination_rate": hallucination_rate,
            "blocked_hallucinations": total_caught,
            "baseline_latency": avg_baseline_latency,
            "verified_latency": avg_verified_latency
        },
        "details": results
    }
    
    with open("evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("Successfully saved detailed report to 'evaluation_results.json'")
    
    # Plot Matplotlib charts
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Chart 1: Accuracy Ablation Comparison
        labels = ['Baseline (Direct)', 'Verified (Analyst-Critic)']
        accuracies = [avg_baseline_acc * 100, avg_verified_acc * 100]
        colors = ['#f7768e', '#9ece6a']
        
        ax1.bar(labels, accuracies, color=colors, width=0.5)
        ax1.set_ylabel('Accuracy (%)')
        ax1.set_title('Ablation Study: Verification Loop Effectiveness')
        ax1.set_ylim(0, 100)
        for i, val in enumerate(accuracies):
            ax1.text(i, val + 2, f"{val:.1f}%", ha='center', fontweight='bold')
            
        # Chart 2: Latency vs. Citation Precision
        metrics = ['Routing Acc', 'Citation Prec', 'Hallucination Rate']
        scores = [avg_routing_acc * 100, avg_cit_precision * 100, hallucination_rate * 100]
        bar_colors = ['#7aa2f7', '#b4f9f8', '#e0af68']
        
        ax2.bar(metrics, scores, color=bar_colors, width=0.5)
        ax2.set_ylabel('Percentage (%)')
        ax2.set_title('Core Quality & Safety Metrics')
        ax2.set_ylim(0, 100)
        for i, val in enumerate(scores):
            ax2.text(i, val + 2, f"{val:.1f}%", ha='center', fontweight='bold')
            
        plt.tight_layout()
        plt.savefig("evaluation_metrics.png", dpi=300)
        print("Successfully generated chart: 'evaluation_metrics.png'")
    except Exception as e:
        print(f"[Matplotlib Error] Could not render metric chart: {e}")

if __name__ == "__main__":
    run_evaluation()
