import re
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
                    "CRITICAL BLUEGENE/L DOMAIN RULES: "
                    "1. SYSTEM ALERTS (Error): Active critical hardware/network faults, specifically: "
                    "   - data TLB error interrupt "
                    "   - data storage interrupt "
                    "   - ciod socket stream failures (failed to read message prefix, failed to fork child) "
                    "   - application or ciod fatal panic/abort "
                    "2. NON-ALERTS (Normal): User-space program events, info messages, and routine kernel operations: "
                    "   - All INFO severity messages (generating core, double-hummer alignment exceptions, CE sym) "
                    "   - Hardware register dumps and user program interrupts (trap instruction, imprecise exception, force load/store alignment) "
                    "   - Any message with corrected"
                ),
                "criteria": {
                    "Normal": "INFO messages, generating core, alignment exceptions, corrected events, trap instructions, register dumps",
                    "Error": "FATAL data TLB error interrupt, FATAL data storage interrupt, ciod socket failures, child process errors"
                }
            }
        }

    def _fast_domain_check(self, text: str) -> Dict[str, Any] | None:
        """
        Tier-1 deterministic classification for known BlueGene/L operational signatures.
        Returns prediction dict if matched, or None if escalated to Laya LLM.
        """
        # Obvious normal: routine INFO severity or hardware-corrected events
        if " corrected" in text or " INFO " in text:
            return {
                "predicted_label": "Normal",
                "confidence": 0.99,
                "probabilities": {"Normal": 0.99, "Error": 0.01},
                "routing_source": "domain_rule"
            }

        # Obvious normal: user-space MPI crash register and state dumps (tagged as '-' in BGL)
        if re.search(r'(instruction address:|data address:|exception syndrome register:|special purpose register:|machine state register:|force load/store alignment|machine check:|program interrupt:|core configuration register:|store operation|problem state|disable store gathering|data address space|\.\.\.\.\.\.\.\.[0-9]|lr:[0-9a-f]{8}|No such file or directory|rts internal error)', text):
            return {
                "predicted_label": "Normal",
                "confidence": 0.99,
                "probabilities": {"Normal": 0.99, "Error": 0.01},
                "routing_source": "domain_rule"
            }

        # Obvious error: critical system hardware/network interrupts
        if re.search(r'(data TLB error interrupt|data storage interrupt|failed to read message prefix|failed to fork child|ciod: Error creating node map)', text):
            return {
                "predicted_label": "Error",
                "confidence": 0.99,
                "probabilities": {"Normal": 0.01, "Error": 0.99},
                "routing_source": "domain_rule"
            }

        return None

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
        Performs fast, high-accuracy batch scoring over constituent lines
        using a two-tier architecture: deterministic domain rules + Laya LLM.
        """
        predictions = {}
        escalate_to_laya = []

        for item in logs:
            lno = item["line_no"]
            fast_res = self._fast_domain_check(item["log_text"])
            if fast_res is not None:
                predictions[lno] = fast_res
            else:
                escalate_to_laya.append(item)

        if escalate_to_laya:
            print(f"Tier-1 classified {len(predictions)} lines. Escalating {len(escalate_to_laya)} lines to Laya LLM...")
            requests = [{"state": item["log_text"], "questions": self.questions} for item in escalate_to_laya]
            results = self.router.predict_batch(requests, batch_size=batch_size)
            for item, res in zip(escalate_to_laya, results):
                answer = res["answers"]["log_status"]
                predictions[item["line_no"]] = {
                    "predicted_label": answer["choice"],
                    "confidence": answer.get("confidence", 0.0),
                    "probabilities": answer.get("probabilities", {}),
                    "routing_source": "laya_llm"
                }

        return predictions

