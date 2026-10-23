from typing import List, Dict, Any
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

def evaluate_predictions(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates True vs Predicted labels and produces a summary report.
    """
    if not records:
        print("No evaluation records found.")
        return {}

    y_true = [r["true_label"] for r in records]
    y_pred = [r["predicted_label"] for r in records]
    labels = ["Normal", "Error"]

    acc = accuracy_score(y_true, y_pred)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    report = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)

    print("\n" + "="*50)
    print("           BGL LOG ANALYSIS EVALUATION REPORT")
    print("="*50)
    print(f"Total Windows Evaluated: {len(records)}")
    print(f"Overall Accuracy:       {acc * 100:.2f}%\n")

    print("Confusion Matrix:")
    print(f"               Predicted Normal   Predicted Error")
    print(f"Actual Normal  {cm[0][0]:<18} {cm[0][1]}")
    print(f"Actual Error   {cm[1][0]:<18} {cm[1][1]}")
    print("\nDetailed Classification Metrics:")
    for lbl in labels:
        metrics = report.get(lbl, {})
        print(f"  [{lbl}] Precision: {metrics.get('precision', 0):.2f} | Recall: {metrics.get('recall', 0):.2f} | F1: {metrics.get('f1-score', 0):.2f}")
    print("="*50 + "\n")

    return {
        "accuracy": acc,
        "confusion_matrix": cm.tolist(),
        "report": report
    }
