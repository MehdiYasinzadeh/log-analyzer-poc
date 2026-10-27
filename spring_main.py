import argparse
import sys
from datetime import datetime
from pymongo import MongoClient
from tqdm import tqdm

from src import config
from src.spring_analyzer import SpringLogParser, SpringIncidentClassifier

def main():
    parser = argparse.ArgumentParser(description="Spring Boot & Enterprise Insurance Log Incident Analyzer")
    parser.add_argument("--log-file", type=str, default="data/ACC-BATCH.log", help="Path to Spring Boot log file")
    parser.add_argument("--max-events", type=int, default=2000, help="Max log events to parse")
    parser.add_argument("--skip-db", action="store_true", help="Skip saving to MongoDB")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("   Spring Boot & Enterprise Insurance Log Analyzer (AIOps Copilot)")
    print("="*70)
    print(f"Target File: {args.log_file}")
    print(f"Max Events:  {args.max_events}")

    # 1. Parse multi-line log events
    print("\n[Step 1/3] Parsing multi-line log events...")
    events = SpringLogParser.parse_file(args.log_file, max_events=args.max_events)
    print(f"Parsed {len(events)} log events successfully.")

    if not events:
        print("No events found. Exiting.")
        sys.exit(0)

    # 2. Database connection
    col = None
    if not args.skip_db:
        try:
            client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            db = client[config.DB_NAME]
            col = db["spring_incidents"]
            print("[Success] Connected to MongoDB (collection: spring_incidents).")
        except Exception as e:
            print(f"[Warning] Could not reach MongoDB: {e}")

    # 3. Analyze and Categorize Incidents
    print("\n[Step 2/3] Analyzing and categorizing incidents...")
    analyzed_records = []
    category_counts = {
        "NORMAL": 0,
        "INFRASTRUCTURE_OUTAGE": 0,
        "BUSINESS_RULE_REJECTION": 0,
        "SOFTWARE_DEFECT": 0,
        "SYSTEM_WARNING": 0
    }

    for evt in tqdm(events, desc="Analyzing Events"):
        analysis = SpringIncidentClassifier.analyze_event(evt)
        category_counts[analysis["category"]] += 1

        record = {
            "event_id": evt["event_id"],
            "source_file": args.log_file,
            "timestamp": evt["timestamp"],
            "level": evt["level"],
            "thread": evt["thread"],
            "header_message": evt["header_message"][:200],
            "category": analysis["category"],
            "category_fa": analysis["category_fa"],
            "severity": analysis["severity"],
            "exception_type": analysis["exception_type"],
            "root_cause": analysis["root_cause"],
            "recommended_action": analysis["recommended_action"],
            "stacktrace_preview": "\n".join(evt["stacktrace"][:5]) if evt["stacktrace"] else "",
            "created_at": datetime.utcnow()
        }
        analyzed_records.append(record)

    # 4. Save to MongoDB
    if col is not None and analyzed_records:
        print("\n[Step 3/3] Persisting incidents to MongoDB...")
        # Upsert in bulk or replace records for this source file
        col.delete_many({"source_file": args.log_file})
        col.insert_many(analyzed_records)
        print(f"Persisted {len(analyzed_records)} analyzed events to MongoDB.")

    # 5. Display Summary Report
    print("\n" + "="*70)
    print("           SPRING BOOT LOG INCIDENT REPORT")
    print("="*70)
    print(f"Total Events Processed: {len(events)}")
    print(f"  • {SpringIncidentClassifier.CATEGORY_LABELS['NORMAL']:<45}: {category_counts['NORMAL']}")
    print(f"  • {SpringIncidentClassifier.CATEGORY_LABELS['INFRASTRUCTURE_OUTAGE']:<45}: {category_counts['INFRASTRUCTURE_OUTAGE']}")
    print(f"  • {SpringIncidentClassifier.CATEGORY_LABELS['BUSINESS_RULE_REJECTION']:<45}: {category_counts['BUSINESS_RULE_REJECTION']}")
    print(f"  • {SpringIncidentClassifier.CATEGORY_LABELS['SOFTWARE_DEFECT']:<45}: {category_counts['SOFTWARE_DEFECT']}")
    print(f"  • {SpringIncidentClassifier.CATEGORY_LABELS['SYSTEM_WARNING']:<45}: {category_counts['SYSTEM_WARNING']}")
    print("="*70)

    # Print top critical incidents
    criticals = [r for r in analyzed_records if r["category"] != "NORMAL"]
    if criticals:
        print(f"\nTop Detected Incidents (Showing first {min(3, len(criticals))}):")
        for i, c in enumerate(criticals[:3], start=1):
            print(f" [{i}] Time: {c['timestamp']} | Level: {c['level']} | Severity: {c['severity']}")
            print(f"     Category: {c['category_fa']}")
            print(f"     Root Cause: {c['root_cause']}")
            print(f"     Recommendation: {c['recommended_action']}\n")

if __name__ == "__main__":
    main()
