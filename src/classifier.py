import torch
from typing import Dict, Any, List

class LayaLogClassifier:
    def __init__(self, model_name: str = "english", device: str = None):
        """
        Initializes Laya Router calibrated specifically for IBM BlueGene/L supercomputer RAS logs.
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
        self.router = Router(default=self.model_name, device=self.device)

        # Calibrated domain question for BlueGene/L alert tagging
        self.questions = {
            "log_status": {
                "type": "choice",
                "instructions": (
                    "You are classifying IBM BlueGene/L supercomputer logs into System Alerts (Error) vs Non-Alerts (Normal). "
                    "CRITICAL DOMAIN RULES: "
                    "1. SYSTEM ALERTS (Error): Active critical hardware/network faults, specifically: "
                    "   - data TLB error interrupts "
                    "   - ciod socket stream failures (failed to read message prefix) "
                    "2. NON-ALERTS (Normal): User-space program events and routine kernel operations, specifically: "
                    "   - program interrupts (trap instruction, imprecise exception) "
                    "   - register dumps (machine state register, store operation) "
                    "   - generating core and INFO logs "
                    "   - messages ending with corrected"
                ),
                "criteria": {
                    "Normal": "user program interrupts, trap instructions, register dumps, core generation, INFO messages, corrected events",
                    "Error": "system hardware faults, data TLB error interrupts, ciod socket communication failures"
                }
            }
        }

    def classify_window(self, window: Dict[str, Any], max_len: int = 4096) -> Dict[str, Any]:
        """
        Classifies a window using domain-specific Laya evaluation.
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

    def classify_lines_batch(self, logs: List[Dict[str, Any]], batch_size: int = 32) -> Dict[int, Dict[str, Any]]:
        """
        Performs fast, high-accuracy batch scoring over all constituent lines.
        """
        requests = [{"state": item["log_text"], "questions": self.questions} for item in logs]
        results = self.router.predict_batch(requests, batch_size=batch_size)
        predictions = {}
        for item, res in zip(logs, results):
            answer = res["answers"]["log_status"]
            predictions[item["line_no"]] = {
                "predicted_label": answer["choice"],
                "confidence": answer.get("confidence", 0.0),
                "probabilities": answer.get("probabilities", {})
            }
        return predictions
