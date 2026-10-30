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


def create_raw_log_sliding_windows(
    file_path: str,
    window_size: int = 25,
    step_size: int = 12,
    max_lines: int = 3000
) -> List[Dict[str, Any]]:
    """
    Creates overlapping sliding windows directly from a raw log file (e.g. Spring Boot).
    Example: window_size=25, step_size=12:
      - Window 0: lines 1 to 25
      - Window 1: lines 13 to 37 (13 lines overlap with Window 0)
      - Window 2: lines 25 to 49 (13 lines overlap with Window 1)
      Overlap percentage: (25 - 12) / 25 * 100 = 52.0%
    """
    raw_lines = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
        for idx, line in enumerate(fp, start=1):
            if idx > max_lines:
                break
            raw_lines.append((idx, line.rstrip("\r\n")))

    total = len(raw_lines)
    windows = []
    w_index = 0
    overlap_lines = max(0, window_size - step_size)
    overlap_pct = round((overlap_lines / window_size) * 100, 1)

    for start_idx in range(0, total, step_size):
        end_idx = min(start_idx + window_size, total)
        chunk = raw_lines[start_idx:end_idx]
        if not chunk:
            break

        start_line_no = chunk[0][0]
        end_line_no = chunk[-1][0]
        combined_text = "\n".join(item[1] for item in chunk)

        windows.append({
            "window_id": f"win_{w_index}_L{start_line_no}_L{end_line_no}",
            "window_index": w_index,
            "start_line": start_line_no,
            "end_line": end_line_no,
            "line_count": len(chunk),
            "window_size": window_size,
            "step_size": step_size,
            "overlap_lines": overlap_lines,
            "overlap_percent": overlap_pct,
            "combined_text": combined_text,
            "lines": [item[1] for item in chunk]
        })
        w_index += 1

        if end_idx >= total:
            break

    print(f"Created {len(windows)} overlapping sliding windows from {file_path}")
    print(f"  Configuration: Window Size={window_size} lines | Step={step_size} lines | Overlap={overlap_lines} lines ({overlap_pct}%)")
    return windows

