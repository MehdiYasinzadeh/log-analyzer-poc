import argparse
import sys
from datetime import datetime
from pymongo import MongoClient
from tqdm import tqdm

from src import config
from src.windowing import create_raw_log_sliding_windows
from src.classifier import LayaLogClassifier
from src.spring_analyzer import SpringIncidentClassifier

def main():
    parser = argparse.ArgumentParser(description="Spring Boot Overlapping Sliding Window Anomaly Detection with Laya")
    parser.add_argument("--log-file", type=str, default="data/ACC-BATCH.log", help="Path to Spring Boot log file")
    parser.add_argument("--max-lines", type=int, default=1500, help="Max lines to read from log file (default: 1500)")
    parser.add_argument("--window-size", type=int, default=25, help="Window size in lines (default: 25)")
    parser.add_argument("--step-size", type=int, default=12, help="Step stride for sliding window (default: 12, ~52% overlap)")
    parser.add_argument("--skip-db", action="store_true", help="Skip persisting to MongoDB")

    args = parser.parse_args()

    overlap_lines = max(0, args.window_size - args.step_size)
    overlap_pct = round((overlap_lines / args.window_size) * 100, 1)

    print("\n" + "="*75)
    print("   Spring Boot AIOps: Overlapping Sliding Window Anomaly Pipeline")
    print("="*75)
    print(f"Log File:     {args.log_file}")
    print(f"Max Lines:    {args.max_lines}")
    print(f"Window Size:  {args.window_size} lines")
    print(f"Step Size:    {args.step_size} lines")
    print(f"Overlap:      {overlap_lines} lines ({overlap_pct}%)")

    # 1. Generate Overlapping Windows
    print("\n[Step 1/3] Generating overlapping sliding windows...")
    windows = create_raw_log_sliding_windows(
        file_path=args.log_file,
        window_size=args.window_size,
        step_size=args.step_size,
        max_lines=args.max_lines
    )

    if not windows:
        print("No windows created. Exiting.")
        sys.exit(1)

    # 2. Database Connection
    col = None
    if not args.skip_db:
        try:
            client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            db = client[config.DB_NAME]
            col = db["spring_window_incidents"]
            # Ensure indexes
            col.create_index("window_id")
            col.create_index("source_file")
            print("[Success] Connected to MongoDB (collection: spring_window_incidents).")
        except Exception as e:
            print(f"[Warning] Could not reach MongoDB at {config.MONGO_URI}: {e}")

    # 3. Layer 1: Laya Gatekeeper Anomaly Detection on Windows
    print(f"\n[Step 2/3] Evaluating {len(windows)} overlapping windows through Laya Gatekeeper...")
    classifier = LayaLogClassifier(model_name="english")
    predictions = classifier.classify_windows_batch(windows, batch_size=16)

    # 4. Layer 2: Deep Incident Extraction & Categorization for Anomalies
    print("\n[Step 3/3] Extracting root causes and classifying detected incidents...")
    analyzed_windows = []
    category_counts = {
        "NORMAL": 0,
        "INFRASTRUCTURE_OUTAGE": 0,
        "TRANSACTION_FAILURE": 0,
        "SOFTWARE_DEFECT": 0,
        "BUSINESS_RULE_REJECTION": 0
    }

    anomaly_count = 0
    for win, pred in zip(windows, predictions):
        analysis = SpringIncidentClassifier.analyze_window(win, pred)
        cat = analysis["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

        if analysis["is_anomaly"]:
            anomaly_count += 1

        doc = {
            "window_id": win["window_id"],
            "window_index": win["window_index"],
            "source_file": args.log_file,
            "start_line": win["start_line"],
            "end_line": win["end_line"],
            "window_size": win["window_size"],
            "step_size": win["step_size"],
            "overlap_lines": win["overlap_lines"],
            "overlap_percent": win["overlap_percent"],
            "is_anomaly": analysis["is_anomaly"],
            "confidence": analysis["confidence"],
            "category": analysis["category"],
            "category_fa": analysis["category_fa"],
            "severity": analysis["severity"],
            "exception_type": analysis["exception_type"],
            "root_cause": analysis["root_cause"],
            "recommended_action": analysis["recommended_action"],
            "timestamp": analysis["timestamp"],
            "thread": analysis["thread"],
            "snippet": analysis["snippet"],
            "updated_at": datetime.utcnow()
        }
        analyzed_windows.append(doc)

    # 5. Persist to MongoDB
    if col is not None and analyzed_windows:
        print("Persisting analyzed windows to MongoDB...")
        col.delete_many({"source_file": args.log_file})
        col.insert_many(analyzed_windows)
        print(f"Successfully stored {len(analyzed_windows)} windows in MongoDB.")

    # 6. Summary Report
    print("\n" + "="*75)
    print("           SPRING BOOT AIOps WINDOW EVALUATION REPORT")
    print("="*75)
    print(f"Total Windows Evaluated:  {len(windows)}")
    print(f"Normal Windows:          {category_counts.get('NORMAL', 0)}")
    print(f"Anomaly Windows (Errors):{anomaly_count}")
    print("\nBreakdown by Incident Category:")
    for cat_key, count in category_counts.items():
        if count > 0 and cat_key != "NORMAL":
            fa_label = SpringIncidentClassifier.CATEGORY_LABELS.get(cat_key, cat_key)
            print(f"  • {fa_label:<45}: {count} پنجره")
    print("="*75)

    # Show top detected incidents
    anomalies = [w for w in analyzed_windows if w["is_anomaly"]]
    if anomalies:
        print(f"\nTop Detected Incidents (Showing first {min(3, len(anomalies))}):")
        for i, a in enumerate(anomalies[:3], start=1):
            print(f" [{i}] {a['window_id']} (Lines {a['start_line']}..{a['end_line']}) | Time: {a['timestamp']}")
            print(f"     Severity: {a['severity']} | Category: {a['category_fa']}")
            print(f"     Root Cause: {a['root_cause']}")
            print(f"     Action: {a['recommended_action']}\n")

if __name__ == "__main__":
    main()
