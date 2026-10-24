# BGL Log Anomaly Detection PoC

A Proof-of-Concept for system log anomaly detection using [Laya](https://github.com/NandhaKishorM/laya) (local decision model with Apple Silicon MPS acceleration), MongoDB for persistence, and a real-time Streamlit dashboard.

## Project Structure

```text
bgl-log-analyzer-poc/
├── config/             # Configuration settings
├── data/               # Datasets:
│   ├── BGL_sample.log  # 2,000 log slice
│   ├── BGL_full.log    # Complete official BGL dataset (4,747,963 lines - 709MB)
│   └── bgl2.gz         # Compressed archive from USENIX
├── doc/                # Documentation & setup checklist
│   └── poc_setup_checklist.md
├── mongo_data/         # Persistent MongoDB storage on local host
├── src/
│   ├── ingestion.py    # Log loader & label separator
│   ├── windowing.py    # Overlapping sliding window generator
│   ├── classifier.py   # Laya Router model integration (MPS accelerated)
│   ├── database.py     # MongoDB manager for windows and line-level predictions
│   └── evaluate.py     # Accuracy, Precision, Recall & Confusion Matrix
├── main.py             # Pipeline execution script
├── dashboard.py        # Real-time Streamlit visualization app
├── docker-compose.yml  # MongoDB container with local volume mount
├── requirements.txt    # Python dependencies
└── README.md
```

## Quick Start Flow

### 1. Start MongoDB (via Docker)
```bash
docker compose up -d
```

### 2. Launch the Real-Time Dashboard
```bash
.venv/bin/streamlit run dashboard.py --server.port 8501
```
Open **`http://localhost:8501`** in your browser to watch live metrics, heatmaps, and timelines.

### 3. Run the Log Analysis Pipeline
In another terminal, stream predictions directly into MongoDB:

```bash
# Run on sample logs
.venv/bin/python main.py --log-file data/BGL_sample.log --window-size 50 --step-size 25

# Or run on full logs with custom slice:
.venv/bin/python main.py --log-file data/BGL_full.log --max-lines 5000 --window-size 100 --step-size 50
```
As `main.py` processes each window, the dashboard automatically updates in real-time!
