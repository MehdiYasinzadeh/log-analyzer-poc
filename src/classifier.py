import torch
from typing import Dict, Any, List

class LayaLogClassifier:
    def __init__(self, model_name: str = "multilingual", device: str = None):
        """
        Initializes the Laya Router for log classification.
        """
        from laya import Router

        if device is None:
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = device

        self.model_name = model_name
        print(f"Initializing Laya Router (model: {self.model_name}, device: {self.device})...")
        self.router = Router(device=self.device)

        # Question definition for Laya typed classification
        self.questions = {
            "log_status": {
                "type": "choice",
                "instructions": (
                    "Analyze the given system log entries. Determine whether they represent "
                    "normal system operation or contain anomalies, errors, hardware/software faults, "
                    "parity errors, or fatal exceptions."
                ),
                "criteria": {
                    "Error": "contains alerts, fatal errors, machine checks, parity failures, hardware faults, or unexpected exceptions",
                    "Normal": "standard operational messages, informational notices, routine diagnostics, healthy system state"
                }
            }
        }

    def classify_window(self, window: Dict[str, Any], max_len: int = 4096) -> Dict[str, Any]:
        """
        Runs Laya forward pass on the window's combined text.
        """
        result = self.router.predict(
            window["combined_text"],
            self.questions,
            model=self.model_name,
            max_len=max_len
        )

        answer = result["answers"]["log_status"]
        predicted_choice = answer["choice"]
        confidence = answer.get("confidence", 0.0)
        probabilities = answer.get("probabilities", {})

        return {
            "predicted_label": predicted_choice,
            "confidence": confidence,
            "probabilities": probabilities,
            "routing_model": result.get("routing", {}).get("model", self.model_name)
        }
