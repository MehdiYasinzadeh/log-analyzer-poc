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
    parser.add_argument("--max-lines", type=int, default=1000, help="Max lines to read")
    parser.add_argument("--window-size", type=int, default=config.DEFAULT_WINDOW_SIZE, help="Number of log lines per window (default: 10)")
    parser.add_argument("--step-size", type=int, default=config.DEFAULT_STEP_SIZE, help="Step stride for sliding window (default: 5)")
    parser.add_argument("--model", type=str, default=config.MODEL_NAME, help="Laya model (default: english)")
    parser.add_argument("--skip-db", action="store_true", help="Run without persisting to MongoDB")

    args = parser.parse_args()

    print("\n" + "="*60)
    print("   BGL Supercomputer Anomaly Detection Pipeline (Optimized)")
    print("="*60)
    print(f"Log File:    {args.log_file}")
    print(f"Max Lines:   {args.max_lines}")
    print(f"Window:      {args.window_size} lines | Step: {args.step_size} lines (Overlap: {args.window_size - args.step_size} lines)")
    print(f"Model:       Laya ({args.model})")

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
            db = None
        else:
            print("[Success] Connected to MongoDB.")

    # 4. Classifier
    classifier = LayaLogClassifier(model_name=args.model)

    # 5. Line-by-Line Batch Inference (Fast & High-Accuracy)
    print(f"\n[Step 1/2] Classifying {len(logs)} log lines with Laya batch inference...")
    line_predictions = classifier.classify_lines_batch(logs, batch_size=32)

    if db:
        print("Persisting line-by-line predictions to MongoDB...")
        db.save_batch_line_results(logs, line_predictions)

    # Line-level Evaluation
    line_eval_records = [
        {"true_label": item["ground_truth"], "predicted_label": line_predictions[item["line_no"]]["predicted_label"]}
        for item in logs
    ]
    print("\n--- Line-by-Line Evaluation Report ---")
    evaluate_predictions(line_eval_records)

    # 6. Window-level Inference & Persistence
    print(f"\n[Step 2/2] Evaluating {len(windows)} sliding windows...")
    window_eval_records = []

    for win in tqdm(windows, desc="Processing Windows"):
        # Window prediction: Flagged as Error if any constituent line is predicted as Error
        has_pred_error = any(
            line_predictions.get(item["line_no"], {}).get("predicted_label") == "Error"
            for item in win["logs"]
        )
        win_predicted_choice = "Error" if has_pred_error else "Normal"

        pred_result = {
            "predicted_label": win_predicted_choice,
            "confidence": 0.90 if win_predicted_choice == "Normal" else 0.85,
            "probabilities": {"Normal": 0.1 if win_predicted_choice == "Error" else 0.9,
                              "Error": 0.9 if win_predicted_choice == "Error" else 0.1}
        }

        record = {
            "window_id": win["window_id"],
            "true_label": win["ground_truth"],
            "predicted_label": win_predicted_choice
        }
        window_eval_records.append(record)

        if db:
            db.save_window_result(win, pred_result)

    print("\n--- Overlapping Window Evaluation Report ---")
    evaluate_predictions(window_eval_records)
    print("\nPipeline execution completed successfully.")

if __name__ == "__main__":
    main()
