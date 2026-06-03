"""
NMS (Non-Maximum Suppression) and object filtering utilities.
"""

import numpy as np


def compute_iou(box1: np.ndarray, box2: np.ndarray) -> float:
    """
    Compute Intersection-over-Union between two axis-aligned boxes.

    Args:
        box1, box2: [x1, y1, x2, y2] in pixels.

    Returns:
        IoU score in [0, 1].
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def nms_detections(
    detections: list,
    iou_threshold: float = 0.5,
) -> list:
    """
    Apply Non-Maximum Suppression to a list of detections.

    Keeps the highest-scoring detection in each group of overlapping boxes.

    Args:
        detections: List of objects with `.box` (np.ndarray [x1,y1,x2,y2])
                    and `.score` (float) attributes.
        iou_threshold: IoU above which boxes are considered overlapping.

    Returns:
        Filtered list of detections.
    """
    if not detections:
        return []

    # Sort by score descending
    sorted_dets = sorted(detections, key=lambda d: d.score, reverse=True)
    keep_indices = []

    for i, det in enumerate(sorted_dets):
        box_i = det.box
        suppressed = False

        for j in keep_indices:
            det_j = sorted_dets[j]
            iou = compute_iou(box_i, det_j.box)
            if iou > iou_threshold:
                suppressed = True
                break

        if not suppressed:
            keep_indices.append(i)

    return [sorted_dets[i] for i in keep_indices]


def nms_masks(
    masks_scores: list[tuple[np.ndarray, float]],
    iou_threshold: float = 0.5,
) -> list[tuple[np.ndarray, float]]:
    """
    Apply NMS directly on binary masks (pixel-level IoU).

    Slower than box-based NMS but more accurate for SAM2 masks.

    Args:
        masks_scores: List of (HxW bool mask, score) tuples.
        iou_threshold: IoU above which masks are merged.

    Returns:
        Filtered list of (mask, score) tuples.
    """
    if not masks_scores:
        return []

    # Sort by score descending
    sorted_masks = sorted(masks_scores, key=lambda x: x[1], reverse=True)
    keep = []

    for i, (mask_i, score_i) in enumerate(sorted_masks):
        suppressed = False
        for j, (mask_j, _) in enumerate(keep):
            intersection = np.logical_and(mask_i, mask_j).sum()
            union = np.logical_or(mask_i, mask_j).sum()
            iou = float(intersection) / float(union) if union > 0 else 0.0
            if iou > iou_threshold:
                suppressed = True
                break

        if not suppressed:
            keep.append((mask_i, score_i))

    return keep


def filter_small_masks(
    masks_scores: list[tuple[np.ndarray, float]],
    min_area: int = 500,
) -> list[tuple[np.ndarray, float]]:
    """
    Remove masks that cover fewer than min_area pixels.

    Args:
        masks_scores: List of (HxW bool mask, score) tuples.
        min_area: Minimum pixel count to keep the mask.

    Returns:
        Filtered list.
    """
    return [(m, s) for m, s in masks_scores if int(m.sum()) >= min_area]
