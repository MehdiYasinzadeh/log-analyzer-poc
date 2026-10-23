import os
from typing import List, Dict, Any

def parse_bgl_line(line: str, line_no: int) -> Dict[str, Any]:
    """
    Parses a single line from the BGL log dataset.
    The first column is the label tag:
      '-' -> Normal (non-alert)
      Anything else (e.g. 'FATAL', 'ERROR', 'FAILURE', ...) -> Error (alert)
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split(maxsplit=1)
    tag = parts[0]
    raw_content = parts[1] if len(parts) > 1 else ""

    # Determine ground truth label
    ground_truth = "Normal" if tag == "-" else "Error"

    return {
        "line_no": line_no,
        "alert_tag": tag,
        "ground_truth": ground_truth,
        "log_text": raw_content
    }

def load_bgl_logs(file_path: str, max_lines: int = None) -> List[Dict[str, Any]]:
    """
    Loads and parses BGL log file into structured entries with ground truth labels stripped.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Log file not found: {file_path}")

    logs = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, start=1):
            if max_lines and idx > max_lines:
                break
            entry = parse_bgl_line(line, line_no=idx)
            if entry:
                logs.append(entry)

    print(f"Loaded {len(logs)} logs from {file_path}")
    return logs
