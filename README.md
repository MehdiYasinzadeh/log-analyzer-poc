# BGL Log Anomaly Detection PoC

A Proof-of-Concept for system log anomaly detection using [Laya](https://github.com/NandhaKishorM/laya) (local decision model with Apple Silicon MPS acceleration) and MongoDB for persistence.

## Project Structure

```text
bgl-log-analyzer-poc/
├── config/             # Configuration settings
├── data/               # Raw BGL logs (BGL_sample.log)
├── mongo_data/         # Persistent MongoDB storage on local host
├── src/
│   ├── ingestion.py    # Log loader & label separator
│   ├── windowing.py    # Overlapping sliding window generator
│   ├── classifier.py   # Laya Router model integration (MPS accelerated)
│   ├── database.py     # MongoDB manager for windows and line-level predictions
│   └── evaluate.py     # Accuracy, Precision, Recall & Confusion Matrix
├── main.py             # Main end-to-end execution script
├── docker-compose.yml  # Docker Compose for MongoDB with volume mount
├── requirements.txt    # Python dependencies
└── README.md
```

## Running the Project

### 1. Start MongoDB (via Docker)
```bash
docker compose up -d
```
The database files are stored in `./mongo_data` so data persists across restarts.

### 2. Run the Analysis Pipeline
```bash
.venv/bin/python main.py --log-file data/BGL_sample.log --window-size 50 --step-size 25
```

### 3. Check MongoDB Records
```bash
.venv/bin/python -c "
from src.database import MongoDBManager
db = MongoDBManager()
print('Windows:', db.windows_col.count_documents({}))
print('Lines:', db.lines_col.count_documents({}))
"
```
