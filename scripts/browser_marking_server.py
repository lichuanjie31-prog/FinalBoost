"""Start a real isolated backend for Tencent marking browser acceptance.

The backend is the real one; only the Tencent SDK boundary is replaced, by
MARKING_MODE=fixture. Every other layer — HTTP, persistence, pacing, polling and
result mapping — is exercised unmodified.
"""
import os
import sys
import tempfile
from pathlib import Path

import uvicorn

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from app.main import create_app

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='finalboost-marking-') as folder:
        uvicorn.run(create_app(data_dir=Path(folder), grading_mode='mock'),
                    host='127.0.0.1', port=int(os.getenv('PORT', '8002')), log_level='warning')
