"""Database module shim.

Keeps backward compatibility for imports like `from api.database import ...`
while delegating implementation to the project-level `database.py`.
"""

from database import *  # noqa: F403,F401
