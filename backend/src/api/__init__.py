"""API layer placeholder.

Future home of FastAPI routers that expose training and simulation flows
from src.services as HTTP endpoints consumable by a frontend.

Example future structure:
    src/api/
    ├── __init__.py
    ├── router.py          ← main APIRouter with all sub-routers
    ├── routes/
    │   ├── training.py    ← POST /train
    │   └── simulation.py  ← POST /simulate, GET /simulate/{id}
    ├── schemas/           ← Pydantic request/response models
    │   ├── training.py
    │   └── simulation.py
    └── dependencies.py    ← FastAPI dependency injection helpers
"""
