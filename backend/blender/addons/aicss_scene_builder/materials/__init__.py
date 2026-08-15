"""Blender materials package."""
from .paper_material import (
    build_paper_node_graph,
    apply_paper_material,
    PaperMaterialParams,
)

__all__ = (
    "build_paper_node_graph",
    "apply_paper_material",
    "PaperMaterialParams",
)