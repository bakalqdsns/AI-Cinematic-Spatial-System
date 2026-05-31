# ─────────────────────────────────────────────────────────────────────────────
# Models package init — re-export the singleton instance
# ─────────────────────────────────────────────────────────────────────────────
from app.models.model_manager import model_manager

__all__ = ["model_manager"]
