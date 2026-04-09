"""
AI-Layer Service Registry
==========================
Each service is a FastAPI APIRouter that wraps the original project's
business logic.  The gateway imports these routers and mounts them
under /api/<service-name>/ prefixes.

Module-level import conflicts (e.g. multiple 'feature_engineering.py'
across projects) are handled via importlib + sys.modules cleanup
inside each service's init() function.
"""
import os
import sys
import importlib.util
from typing import Any

BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def get_service_dir(folder_name: str) -> str:
    """Return absolute path to a service project folder."""
    return os.path.normpath(os.path.join(BASE_DIR, folder_name))


def safe_import(service_dir: str, module_name: str) -> Any:
    """
    Import a module from a specific service directory, avoiding cache
    collisions with identically-named modules in other services.

    1. Purge any existing module with `module_name` from sys.modules.
    2. Insert service_dir at front of sys.path.
    3. Import the module (internal imports resolve correctly).
    4. Remove service_dir from sys.path.
    5. Purge the bare name from sys.modules (keep the reference).

    The caller keeps a direct reference to the returned module object,
    so later cache cleanup does NOT break it.
    """
    # Purge cached version (from a different service)
    for key in list(sys.modules.keys()):
        if key == module_name or key.startswith(module_name + "."):
            del sys.modules[key]

    # Temporarily add service dir
    sys.path.insert(0, service_dir)
    try:
        module = importlib.import_module(module_name)
    finally:
        try:
            sys.path.remove(service_dir)
        except ValueError:
            pass

    return module
