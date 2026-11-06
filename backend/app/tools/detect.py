"""物件检测工具 —— GroundingDINO + SAM2。

包装 ``app.services.object_detector.detect_objects``。输出 dataclass
（``DetectResult``），里面的 ``objects`` 可以直接喂给
``classify_scene`` / ``split_layers`` / ``fill_occlusions`` 继续用；
需要 JSON 时调 ``DetectResult.to_dict()``。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.tools._shared import ImageLike, to_pil

__all__ = ["detect_objects", "DetectResult"]


@dataclass
class DetectResult:
    """物件检测结果。

    字段:
        objects: ``app.services.object_assets.ObjectAsset`` 列表，每项带
            label / score / bbox / mask / depth_mean / layer_hint /
            rgba 抠图等，可直接传给分层与场景分类工具。
        ground_entries: 地面类候选 ``(detection, mask)`` 列表，供
            ``app.services.ground_reconstructor.reconstruct_ground`` 使用。
    """

    objects: list = field(default_factory=list)
    ground_entries: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """转成 JSON 友好的 dict（不含 mask / PIL 图像等大对象）。

        输出形状::

            {
              "objects": [{object_id, label, score, bbox, depth_mean,
                           depth_min, depth_max, layer_hint, z_offset, meta}],
              "ground_candidate_count": int,
            }
        """
        items = []
        for obj in self.objects:
            items.append({
                "object_id": getattr(obj, "object_id", ""),
                "label": getattr(obj, "label", ""),
                "score": float(getattr(obj, "score", 0.0)),
                "bbox": [int(v) for v in (getattr(obj, "bbox", None) or ())],
                "depth_mean": float(getattr(obj, "depth_mean", 0.0)),
                "depth_min": float(getattr(obj, "depth_min", 0.0)),
                "depth_max": float(getattr(obj, "depth_max", 0.0)),
                "layer_hint": getattr(obj, "layer_hint", ""),
                "z_offset": float(getattr(obj, "z_offset", 0.0)),
                "meta": dict(getattr(obj, "meta", None) or {}),
            })
        return {
            "objects": items,
            "ground_candidate_count": len(self.ground_entries),
        }


def detect_objects(
    image: ImageLike,
    depth_meters: Optional[np.ndarray] = None,
    scene_type: str = "outdoor",
    prompt: Optional[list[str]] = None,
    confidence_threshold: float = 0.3,
    max_objects: int = 32,
    min_mask_area_px: int = 256,
) -> DetectResult:
    """检测图像中的物件并逐件抠图（GroundingDINO 框 + SAM2 mask）。

    输入:
        image: PIL 图像 / numpy 数组 / 图像文件路径。
        depth_meters: HxW 米制深度（``estimate_depth`` 的输出），用于给
            每件物体算 depth_mean / min / max；None 时深度字段为 0。
        scene_type: "outdoor" / "indoor" / "night" / "nature"，决定默认
            检测词表。
        prompt: 自定义检测词列表（如 ["person", "bicycle"]）；给了就忽略
            scene_type 的默认词表。地面类名词总会自动追加。
        confidence_threshold: GroundingDINO 置信度阈值。
        max_objects: 最多保留的物件数（按分数排序截断）。
        min_mask_area_px: 小于该面积的 mask 丢弃。
    输出:
        ``DetectResult``。``result.objects`` 可直接传给
        ``classify_scene`` / ``split_layers`` / ``fill_occlusions``；
        JSON 化用 ``result.to_dict()``。
    副作用:
        无（首次懒加载模型会占显存）。
    模型:
        GroundingDINO（GPU）+ SAM2（GPU），从
        ``app.models.model_manager`` 懒加载。
    """
    from app.services.object_detector import detect_objects as _detect

    pil = to_pil(image, mode="RGB")
    objects, ground_entries = _detect(
        pil,
        depth_meters,
        prompt=prompt,
        scene_type=scene_type,
        confidence_threshold=confidence_threshold,
        max_objects=max_objects,
        min_mask_area_px=min_mask_area_px,
    )
    return DetectResult(objects=objects, ground_entries=ground_entries)
