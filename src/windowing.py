from typing import List, Dict, Any, Generator

def create_sliding_windows(
    logs: List[Dict[str, Any]],
    window_size: int = 50,
    step_size: int = 25
) -> List[Dict[str, Any]]:
    """
    Creates overlapping sliding windows from the parsed logs.
    E.g. with window_size=50, step_size=25:
      Window 1: lines 0 to 50
      Window 2: lines 25 to 75
      Window 3: lines 50 to 100
    """
    total = len(logs)
    windows = []
    w_index = 0

    for start_idx in range(0, total, step_size):
        end_idx = min(start_idx + window_size, total)
        chunk = logs[start_idx:end_idx]
        if not chunk:
            break

        # Ground truth for window: if any log has Error, window is considered Error
        has_error = any(item["ground_truth"] == "Error" for item in chunk)
        window_ground_truth = "Error" if has_error else "Normal"

        # Combine log texts without the ground truth labels
        combined_text = "\n".join(
            f"[{item['line_no']}] {item['log_text']}" for item in chunk
        )

        windows.append({
            "window_id": f"win_{w_index}_{chunk[0]['line_no']}_{chunk[-1]['line_no']}",
            "start_line": chunk[0]["line_no"],
            "end_line": chunk[-1]["line_no"],
            "log_count": len(chunk),
            "ground_truth": window_ground_truth,
            "has_error_lines": [item["line_no"] for item in chunk if item["ground_truth"] == "Error"],
            "logs": chunk,
            "combined_text": combined_text
        })
        w_index += 1

        if end_idx >= total:
            break

    print(f"Created {len(windows)} overlapping windows (size={window_size}, step={step_size}, overlap={window_size - step_size})")
    return windows
