import os

# MongoDB Settings
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "log_analysis")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "bgl_predictions")

# Windowing Settings
DEFAULT_WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "20"))  # 20 lines is optimal for log focus
DEFAULT_STEP_SIZE = int(os.getenv("STEP_SIZE", "10"))     # 50% overlap

# Model Settings
MODEL_NAME = os.getenv("LAYA_MODEL", "english")  # ModernBERT-large English is best for Linux/HPC logs
MAX_TOKENS = int(os.getenv("LAYA_MAX_LEN", "4096"))
DEVICE = os.getenv("DEVICE", "mps")
