import argparse
import sys
from tqdm import tqdm

from src import config
from src.ingestion import load_bgl_logs
from src.windowing import create_sliding_windows
from src.classifier import LayaLogClassifier
from src.database import MongoDBManager
from src.evaluate import evaluate_predictions

def main():
    parser = argparse.ArgumentParser(description="BGL Log Anomaly Detection PoC with Laya & MongoDB")
    parser.add_argument("--log-file", type=str, default="data/BGL_sample.log", help="Path to raw BGL log file")
    parser.add_argument("--max-lines", type=int, default=1000, help="Max lines to read from the log file (for quick PoC testing)")
    parser.add_argument("--window-size", type=int, default=config.DEFAULT_WINDOW_SIZE, help="Number of log lines per window")
    parser.add_argument("--step-size", type=int, default=config.DEFAULT_STEP_SIZE, help="Step stride for sliding window (overlap = size - step)")
    parser.add_argument("--model", type=str, default=config.MODEL_NAME, help="Laya model name (multilingual / english)")
    parser.add_argument("--skip-db", action="store_true", help="Run without persisting to MongoDB")

    args = parser.parse_args()

    print("\n--- Starting BGL Log Analysis Pipeline ---")
    print(f"Log File: {args.log_file}")
    print(f"Max Lines: {args.max_lines}")
    print(f"Window Size: {args.window_size}, Step Size: {args.step_size} (Overlap: {args.window_size - args.step_size})")

    # 1. Ingestion
    logs = load_bgl_logs(args.log_file, max_lines=args.max_lines)
    if not logs:
        print("No logs loaded. Exiting.")
        sys.exit(1)

    # 2. Windowing
    windows = create_sliding_windows(logs, window_size=args.window_size, step_size=args.step_size)

    # 3. Database connection
    db = None
    if not args.skip_db:
        db = MongoDBManager(uri=config.MONGO_URI, db_name=config.DB_NAME)
        if not db.ping():
            print("[Warning] Could not reach MongoDB at", config.MONGO_URI)
            print("Running in memory-only mode without saving to DB. (Use 'docker-compose up -d' to start Mongo)")
            db = None
        else:
            print("[Success] Connected to MongoDB.")

    # 4. Classifier
    classifier = LayaLogClassifier(model_name=args.model)

    # 5. Process Windows
    print("\nProcessing windows through Laya...")
    evaluated_records = []

    for win in tqdm(windows, desc="Classifying Windows"):
        pred = classifier.classify_window(win, max_len=config.MAX_TOKENS)

        record = {
            "window_id": win["window_id"],
            "true_label": win["ground_truth"],
            "predicted_label": pred["predicted_label"],
            "confidence": pred["confidence"]
        }
        evaluated_records.append(record)

        if db:
            db.save_window_result(win, pred)
            db.save_line_results(win, pred)

    # 6. Evaluation
    evaluate_predictions(evaluated_records)
    print("Pipeline execution completed successfully.")

if __name__ == "__main__":
    main()
