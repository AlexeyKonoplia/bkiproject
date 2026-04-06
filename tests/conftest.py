import sys
from pathlib import Path


def pytest_configure():
    # Добавляем `backend` в PYTHONPATH, чтобы пакет `app` был импортируемым.
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend_dir))

