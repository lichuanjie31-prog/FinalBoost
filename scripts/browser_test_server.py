"""Start a real isolated HTTP backend for browser acceptance tests."""
import sys
import tempfile
from pathlib import Path
import uvicorn

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from app.main import create_app

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='finalboost-browser-') as folder:
        uvicorn.run(create_app(data_dir=Path(folder), grading_mode='mock'), host='127.0.0.1', port=8001, log_level='warning')
