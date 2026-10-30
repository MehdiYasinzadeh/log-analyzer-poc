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

        # Calibrated domain question for Spring Boot & Enterprise Application Logs
        self.questions = {
            "log_status": {
                "type": "choice",
                "instructions": (
                    "You are an AIOps Anomaly Detector evaluating Spring Boot enterprise application log windows. "
                    "Determine if this window contains an active ANOMALY/FAILURE (Error) or NORMAL operations (Normal). "
                    "CRITICAL SPRING BOOT RULES: "
                    "1. ANOMALY / ERROR: "
                    "   - Java Exceptions and stack trace lines (e.g., 'at org...', 'Caused by:', SQLException, JpaSystemException, GenericJDBCException, NullPointerException, TimeoutException, RollbackException) "
                    "   - Database connection acquisition failures, JDBC/Hikari pool exhaustion, transaction rollbacks "
                    "   - Log level ERROR or FATAL, or critical WARN "
                    "   - HTTP 500, 503 Service Unavailable, or failed scheduled batch job executions "
                    "2. NORMAL: "
                    "   - Routine INFO and DEBUG logs without exceptions "
                    "   - Regular job/thread executions without stack traces "
                    "   - Normal database queries, health checks, and transaction commits "
                ),
                "criteria": {
                    "Normal": "routine INFO/DEBUG logs, no stack traces, no exceptions, normal execution",
                    "Error": "Java exceptions, stack trace lines, JDBC connection failures, rollback exceptions, ERROR/FATAL events"
                }
            }
        }

    def _fast_domain_check(self, text: str) -> Dict[str, Any] | None:
        """
        Tier-1 deterministic classification for Spring Boot operational signatures.
        Returns prediction dict if matched, or None if escalated to Laya LLM.
        """
        # 1. Obvious Error / Anomaly: stack traces, ERROR/FATAL levels, thrown exceptions, or connection failures
        has_error = (
            bool(re.search(r'(?:^\s*at\s+[a-zA-Z0-9_.]+\(|Caused by:\s+)', text, re.M)) or
            bool(re.search(r'\b(ERROR|FATAL)\b', text)) or
            bool(re.search(r'\b[a-zA-Z0-9_.]+(?:Exception|Error)(?::|\b)', text)) or
            bool(re.search(r'(Unable to acquire JDBC Connection|Connection refused|SocketTimeoutException|rollback|StatusRuntimeException|Status\{code=UNAVAILABLE|Failed with status)', text, re.I))
        )
        if has_error:
            return {
                "predicted_label": "Error",
                "confidence": 0.99,
                "probabilities": {"Normal": 0.01, "Error": 0.99},
                "routing_source": "domain_rule"
            }

        # 2. Obvious Normal: routine INFO, INFORMATION, DEBUG, or TRACE logs without any error markers
        has_normal_level = bool(re.search(r'\b(INFO|INFORMATION|DEBUG|TRACE)\b', text, re.I))
        if has_normal_level:
            return {
                "predicted_label": "Normal",
                "confidence": 0.99,
                "probabilities": {"Normal": 0.99, "Error": 0.01},
                "routing_source": "domain_rule"
            }

        return None

    def classify_window(self, window: Dict[str, Any], max_len: int = 4096) -> Dict[str, Any]:
        """
        Classifies a window using domain-specific Laya evaluation.
        """
        text = window.get("combined_text", "")
        fast_res = self._fast_domain_check(text)
        if fast_res is not None:
            return {
                "predicted_label": fast_res["predicted_label"],
                "confidence": fast_res["confidence"],
                "probabilities": fast_res["probabilities"],
                "routing_model": "tier1_domain_rule"
            }

        result = self.router.predict(
            text,
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

    def classify_windows_batch(self, windows: List[Dict[str, Any]], batch_size: int = 16) -> List[Dict[str, Any]]:
        """
        Batch-evaluates overlapping sliding windows through Laya.
        """
        results = [None] * len(windows)
        escalate_indices = []

        for idx, win in enumerate(windows):
            fast_res = self._fast_domain_check(win["combined_text"])
            if fast_res is not None:
                results[idx] = {
                    "predicted_label": fast_res["predicted_label"],
                    "confidence": fast_res["confidence"],
                    "probabilities": fast_res["probabilities"],
                    "routing_model": "tier1_fast_check"
                }
            else:
                escalate_indices.append(idx)

        if escalate_indices:
            print(f"Tier-1 classified {len(windows) - len(escalate_indices)} windows. Escalating {len(escalate_indices)} windows to Laya LLM...")
            requests = [{"state": windows[i]["combined_text"], "questions": self.questions} for i in escalate_indices]
            laya_res = self.router.predict_batch(requests, batch_size=batch_size)
            for i, res in zip(escalate_indices, laya_res):
                answer = res["answers"]["log_status"]
                results[i] = {
                    "predicted_label": answer["choice"],
                    "confidence": answer.get("confidence", 0.0),
                    "probabilities": answer.get("probabilities", {}),
                    "routing_model": "laya_llm"
                }

        return results

