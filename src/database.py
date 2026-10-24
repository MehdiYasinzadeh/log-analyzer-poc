from datetime import datetime
from typing import List, Dict, Any
from pymongo import MongoClient, ASCENDING

class MongoDBManager:
    def __init__(self, uri: str = "mongodb://localhost:27017/", db_name: str = "log_analysis"):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.windows_col = self.db["window_predictions"]
        self.lines_col = self.db["line_predictions"]
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.windows_col.create_index([("window_id", ASCENDING)], unique=True)
            self.windows_col.create_index([("start_line", ASCENDING)])
            self.lines_col.create_index([("line_no", ASCENDING)], unique=True)
        except Exception as e:
            print(f"Index creation note: {e}")

    def ping(self) -> bool:
        """Checks if MongoDB connection is alive."""
        try:
            self.client.admin.command('ping')
            return True
        except Exception as e:
            print(f"MongoDB connection failed: {e}")
            return False

    def save_window_result(self, window: Dict[str, Any], prediction: Dict[str, Any]) -> str:
        """
        Saves prediction result for a window alongside ground truth.
        """
        doc = {
            "window_id": window["window_id"],
            "start_line": window["start_line"],
            "end_line": window["end_line"],
            "log_count": window["log_count"],
            "true_label": window["ground_truth"],
            "predicted_label": prediction["predicted_label"],
            "is_correct": window["ground_truth"] == prediction["predicted_label"],
            "confidence": prediction.get("confidence", 0.0),
            "probabilities": prediction.get("probabilities", {}),
            "error_line_numbers": window.get("has_error_lines", []),
            "created_at": datetime.utcnow()
        }

        self.windows_col.update_one(
            {"window_id": doc["window_id"]},
            {"$set": doc},
            upsert=True
        )
        return doc["window_id"]

    def save_batch_line_results(self, logs: List[Dict[str, Any]], line_predictions: Dict[int, Dict[str, Any]]):
        """
        Saves individual line predictions from Laya.
        """
        for item in logs:
            lno = item["line_no"]
            l_pred = line_predictions.get(lno, {})
            line_doc = {
                "line_no": lno,
                "raw_text": item["log_text"],
                "original_alert_tag": item["alert_tag"],
                "true_label": item["ground_truth"],
                "latest_predicted_label": l_pred.get("predicted_label", "Normal"),
                "confidence": l_pred.get("confidence", 0.0),
                "probabilities": l_pred.get("probabilities", {}),
                "is_correct": item["ground_truth"] == l_pred.get("predicted_label", "Normal"),
                "updated_at": datetime.utcnow()
            }
            self.lines_col.update_one(
                {"line_no": lno},
                {"$set": line_doc},
                upsert=True
            )

    def fetch_evaluation_records(self) -> List[Dict[str, Any]]:
        return list(self.windows_col.find({}, {"_id": 0}))
