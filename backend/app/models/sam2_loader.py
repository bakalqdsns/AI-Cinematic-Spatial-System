"""
SAM2 Loader.

SAM2 (Segment Anything Model 2) produces pixel-accurate instance masks.
We initialize from detection boxes (from Grounding DINO) to get precise masks.
"""
import cv2
import torch
import numpy as np
from PIL import Image
from typing import Union, Optional
import sys
import os

# SAM2 is installed via ultralytics or sam2 package
try:
    from sam2.build_sam import build_sam2
    from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
    from sam2.sam2_image_predictor import SAM2ImagePredictor
except ImportError:
    try:
        # Alternative: ultralytics wraps SAM2
        import ultralytics
        SAM2_AVAILABLE = True
    except ImportError:
        print("[SAM2] Warning: SAM2 not installed. Install with: pip install ultralytics")
        SAM2_AVAILABLE = False


class SAM2Model:
    """
    SAM2 mask generator from detection boxes.

    Supports both standalone SAM2 and ultralytics wrapper.

    Usage:
        model = SAM2Model(model_size="vit_l", device="cuda")
        model.load()
        masks = model.predict_masks_from_boxes(image, boxes)  # list of HxW bool masks
    """

    SAM2_CONFIGS = {
        # IMPORTANT: ultralytics expects specific checkpoint names that differ from
        # Meta's official filenames. The "checkpoint" key here MUST match what
        # ultralytics SAM() expects (e.g. 'sam2.1_l.pt', not 'sam2.1_hiera_large.pt').
        # Download URLs point to Meta CDN (dl.fbaipublicfiles.com) with the official names.
        "vit_l": {
            "model_cfg": "sam2.1_hiera_l.yaml",
            "checkpoint": "sam2.1_l.pt",           # ultralytics naming
            "official_name": "sam2.1_hiera_large.pt", # Meta's actual filename for download
            "repo_id": "facebook/sam2.1-hiera-large",
        },
        "vit_h": {
            "model_cfg": "sam2.1_hiera_l.yaml",
            "checkpoint": "sam2.1_l.pt",
            "official_name": "sam2.1_hiera_large.pt",
            "repo_id": "facebook/sam2.1-hiera-large",
        },
        "vit_b": {
            "model_cfg": "sam2.1_hiera_b+.yaml",
            "checkpoint": "sam2.1_b.pt",
            "official_name": "sam2.1_hiera_base_plus.pt",
            "repo_id": "facebook/sam2.1-hiera-base-plus",
        },
        "vit_s": {
            "model_cfg": "sam2.1_hiera_s.yaml",
            "checkpoint": "sam2.1_s.pt",
            "official_name": "sam2.1_hiera_small.pt",
            "repo_id": "facebook/sam2.1-hiera-small",
        },
        "vit_t": {
            "model_cfg": "sam2.1_hiera_t.yaml",
            "checkpoint": "sam2.1_t.pt",
            "official_name": "sam2.1_hiera_tiny.pt",
            "repo_id": "facebook/sam2.1-hiera-tiny",
        },
    }

    def __init__(self, model_size: str = "vit_h", device: str = "cuda",
                 checkpoint_dir: Optional[str] = None):
        self.model_size = model_size
        _effective = device if torch.cuda.is_available() else "cpu"
        self.device = torch.device(_effective)
        if _effective != device:
            print(f"[SAM2] CUDA unavailable — fell back to CPU (requested: {device})")
        # Default: <project-root>/backend/.cache/sam2  (matches config.py sam2_checkpoint_dir)
        # Override with SAM2_CHECKPOINT_DIR env var if needed.
        default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".cache", "sam2")
        self.checkpoint_dir = checkpoint_dir or os.environ.get("SAM2_CHECKPOINT_DIR") or default_dir
        self._predictor: Optional[object] = None
        self._automatic_generator: Optional[object] = None

    def _sam2_repo_id(self) -> str:
        """Return the HuggingFace repo_id for the configured model size."""
        cfg = self.SAM2_CONFIGS.get(self.model_size, self.SAM2_CONFIGS["vit_l"])
        return cfg["repo_id"]

    def ensure_downloaded(self) -> str:
        """
        Ensure the SAM2 checkpoint is on disk. Returns the local file path.

        Download strategy (in order):
          1. HuggingFace Hub (via ``snapshot_download``) — relies on
             ``HF_ENDPOINT=https://hf-mirror.com`` being set in config.py
             so it goes through the China mirror.  Works for vit_l / vit_b.
          2. Meta CDN fallback — ``https://dl.fbaipublicfiles.com/``
             for vit_s / vit_t (hf-mirror doesn't have those) and as a
             universal fallback when HF Hub is unreachable.
          3. Each strategy retries up to 3 times with exponential back-off.

        The download timeout is read from ``HF_HUB_DOWNLOAD_TIMEOUT``
        (defaulting to 600 s if unset).  We always set it here to 600 s
        because ``huggingface_hub``'s hard-coded default is 10 s — far
        too short for the ~375 MB SAM2 checkpoint on slow networks and the
        cause of the ``WinError 10060`` ConnectTimeout seen by users.
        """
        import glob
        import time as _time
        import requests as _requests

        # Defensive: re-set env vars config.py may not have applied yet (e.g.
        # if someone ran this loader directly from a script outside FastAPI).
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        sam2_cfg = self.SAM2_CONFIGS.get(self.model_size, self.SAM2_CONFIGS["vit_l"])
        ultralytics_name = sam2_cfg["checkpoint"]      # e.g. 'sam2.1_l.pt'
        official_name = sam2_cfg.get("official_name", ultralytics_name)  # e.g. 'sam2.1_hiera_large.pt'
        repo_id = self._sam2_repo_id()
        cache_dir = str(self.checkpoint_dir)
        max_retries = int(os.environ.get("HF_DOWNLOAD_RETRIES", "3"))

        timeout_s = int(os.environ["HF_HUB_DOWNLOAD_TIMEOUT"])
        ultralytics_target = os.path.join(cache_dir, ultralytics_name)

        # Already downloaded with ultralytics name? Done.
        if os.path.exists(ultralytics_target):
            print(f"[SAM2] Found cached checkpoint: {ultralytics_target}")
            return ultralytics_target

        # Check if we have the official name already — rename it to ultralytics name
        official_target = os.path.join(cache_dir, official_name)
        if os.path.exists(official_target):
            try:
                os.rename(official_target, ultralytics_target)
                print(f"[SAM2] Renamed {official_name} -> {ultralytics_name}")
                return ultralytics_target
            except OSError:
                # Cross-device or other rename failure — use official name as-is
                print(f"[SAM2] Could not rename {official_name}, using directly")
                return official_target

        os.makedirs(cache_dir, exist_ok=True)

        def _log(msg: str):
            print(f"[SAM2] {msg}")

        last_exc: Exception | None = None

        # ── Strategy 1: HuggingFace Hub (through hf-mirror.com) ───────────────
        # Download the official file, then rename to ultralytics name.
        _log(f"Downloading {repo_id}/{official_name} via HF Hub (timeout={timeout_s}s, retries={max_retries}) ...")
        try:
            from huggingface_hub import snapshot_download

            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    _log(f"  Retry {attempt}/{max_retries} ...")
                    _time.sleep(2 ** attempt)
                try:
                    local_dir = snapshot_download(
                        repo_id=repo_id,
                        cache_dir=cache_dir,
                        allow_patterns=[f"*{official_name}*", "*.yaml"],
                        ignore_patterns=["*.msgpack", "*.gitattributes"],
                    )
                    pattern = os.path.join(local_dir, "**", official_name)
                    matches = glob.glob(pattern, recursive=True)
                    if matches:
                        official_downloaded = matches[0]
                        _log(f"Downloaded: {official_downloaded}")
                        # Rename to ultralytics name
                        try:
                            os.rename(official_downloaded, ultralytics_target)
                            _log(f"Renamed {official_name} -> {ultralytics_name}")
                            return ultralytics_target
                        except OSError:
                            _log(f"Rename failed, using {official_downloaded} directly")
                            return official_downloaded
                    raise FileNotFoundError(
                        f"'{official_name}' not found in {local_dir} after snapshot_download"
                    )
                except Exception as exc:
                    last_exc = exc
                    _log(f"  Attempt {attempt} failed: {type(exc).__name__}: {exc}")

        except ImportError:
            _log("huggingface_hub not installed — skipping HF Hub strategy.")

        # ── Strategy 2: Meta CDN (always public, no auth required) ───────────
        # Download the official file (Meta uses official naming).
        meta_url = (
            f"https://dl.fbaipublicfiles.com/segment_anything_2/092824/{official_name}"
        )
        _log(f"Downloading {official_name} via Meta CDN: {meta_url} (timeout={timeout_s}s, retries={max_retries}) ...")
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                _log(f"  Retry {attempt}/{max_retries} ...")
                _time.sleep(2 ** attempt)
            try:
                with _requests.get(meta_url, timeout=timeout_s, stream=True,
                                   allow_redirects=True) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("Content-Length", 0))
                    written = 0
                    last_pct = -1
                    part_file = official_target + ".part"
                    with open(part_file, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            written += len(chunk)
                            if total > 0:
                                pct = int(written * 100 / total)
                                if pct - last_pct >= 10:
                                    last_pct = pct
                                    mb_w = written // (1024 * 1024)
                                    mb_t = total // (1024 * 1024)
                                    _log(f"  {pct}%  ({mb_w}/{mb_t} MB)")
                    os.replace(part_file, official_target)
                    size_mb = os.path.getsize(official_target) // (1024 * 1024)
                    _log(f"Downloaded: {official_target} ({size_mb} MB)")
                    # Rename to ultralytics name
                    try:
                        os.rename(official_target, ultralytics_target)
                        _log(f"Renamed {official_name} -> {ultralytics_name}")
                        return ultralytics_target
                    except OSError:
                        _log(f"Rename failed, using {official_target} directly")
                        return official_target
            except Exception as exc:
                last_exc = exc
                _log(f"  Attempt {attempt} failed: {type(exc).__name__}: {exc}")
                if os.path.exists(official_target + ".part"):
                    try:
                        os.remove(official_target + ".part")
                    except OSError:
                        pass

        raise RuntimeError(
            f"SAM2 checkpoint download failed after {max_retries} attempts "
            f"for {ultralytics_name} (official: {official_name}). Tried: HF Hub ({repo_id}), Meta CDN ({meta_url}). "
            f"Check network / HF_ENDPOINT / HF_HUB_DOWNLOAD_TIMEOUT."
        ) from last_exc

    def load(self):
        """Load SAM2 model. Downloads checkpoint on first run."""
        print(f"[SAM2] Loading SAM2 ({self.model_size}) on {self.device}...")

        if SAM2_AVAILABLE:
            self._load_sam2_ultralytics()
        else:
            self._load_sam2_standalone()
        print("[SAM2] Loaded.")

    def _load_sam2_ultralytics(self):
        """Load via ultralytics — simplest installation path."""
        # Hygiene: point ultralytics at the project cache so SAM2 weights
        # land in the same place as the rest of AICSS, not in the cwd or
        # whatever weights_dir the user has set globally (e.g. for
        # stable-diffusion-webui).  This must run *before* ``SAM(...)`` is
        # constructed since ``SAM`` triggers the download at __init__.
        try:
            from ultralytics import settings as _u_settings
            _u_settings.update({"weights_dir": str(self.checkpoint_dir)})
        except Exception:
            pass

        from ultralytics import SAM

        sam2_cfg = self.SAM2_CONFIGS.get(self.model_size, self.SAM2_CONFIGS["vit_l"])
        ultralytics_name = sam2_cfg["checkpoint"]      # e.g. 'sam2.1_l.pt'
        official_name = sam2_cfg.get("official_name", ultralytics_name)  # e.g. 'sam2.1_hiera_large.pt'

        # Search order:
        # 1. ultralytics name in project cache
        # 2. official name in project cache
        # 3. Any .pt file in project cache (fallback)
        # 4. Let ultralytics auto-download
        import os as _os
        import glob as _glob

        weight_arg = None

        # Check ultralytics name first
        candidate1 = _os.path.join(self.checkpoint_dir, ultralytics_name)
        if _os.path.exists(candidate1):
            weight_arg = candidate1
            print(f"[SAM2] Found checkpoint: {ultralytics_name}")

        # Check official name
        if weight_arg is None and official_name != ultralytics_name:
            candidate2 = _os.path.join(self.checkpoint_dir, official_name)
            if _os.path.exists(candidate2):
                # Rename to ultralytics name
                try:
                    _os.rename(candidate2, candidate1)
                    weight_arg = candidate1
                    print(f"[SAM2] Renamed {official_name} -> {ultralytics_name}")
                except OSError:
                    # Cross-device rename fails; just use the official name
                    weight_arg = candidate2
                    print(f"[SAM2] Using checkpoint: {official_name} (rename failed)")

        # Scan for any .pt file as last resort
        if weight_arg is None:
            for pt_file in _glob.glob(_os.path.join(self.checkpoint_dir, "*.pt")):
                if _os.path.basename(pt_file) != ultralytics_name:
                    print(f"[SAM2] Found alternative checkpoint: {pt_file}, using for {ultralytics_name}")
                    # Copy to expected location for ultralytics
                    import shutil
                    try:
                        shutil.copy2(pt_file, candidate1)
                        weight_arg = candidate1
                    except Exception:
                        weight_arg = pt_file
                    break

        # Fall back to auto-download
        if weight_arg is None:
            weight_arg = ultralytics_name

        predictor = SAM(weight_arg)
        self._predictor = predictor
        print(f"[SAM2] Loaded via ultralytics: {predictor.model_name if hasattr(predictor, 'model_name') else weight_arg}")

    def _resolve_ckpt_path(self, checkpoint_name: str) -> Optional[str]:
        """
        Locate a SAM2 checkpoint by name within the huggingface hub cache.
        Returns the full path if found, None otherwise.
        """
        import glob
        # 优先读取 config.py 已通过 HF_HUB_CACHE 环境变量重定向后的路径，
        # 保证 SAM2 checkpoint 回退查找仍走 backend/.cache/huggingface/hub，
        # 与项目其它模型的缓存位置保持一致；只有在环境变量未设置时才回退到 ~/.cache/huggingface/hub。
        hf_hub_dir = os.environ.get("HF_HUB_CACHE") or os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface", "hub"
        )
        for root in [self.checkpoint_dir, hf_hub_dir]:
            pattern = os.path.join(root, "**", "snapshots", "**", checkpoint_name)
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return matches[0]
            # Also try matching any file containing the checkpoint name
            pattern2 = os.path.join(root, "**", checkpoint_name)
            matches2 = glob.glob(pattern2, recursive=True)
            if matches2:
                return matches2[0]
        return None

    def _load_sam2_standalone(self):
        """Load standalone SAM2 from Meta's repository."""
        sam2_cfg = self.SAM2_CONFIGS.get(self.model_size, self.SAM2_CONFIGS["vit_h"])
        ckpt_name = sam2_cfg["checkpoint"]

        # Try to resolve from cache first, otherwise auto-download.
        ckpt_path = self._resolve_ckpt_path(ckpt_name)
        if ckpt_path is None:
            print(f"[SAM2] Checkpoint '{ckpt_name}' not found in cache — downloading...")
            ckpt_path = self.ensure_downloaded()

        try:
            sam2_model = build_sam2(
                config_file=sam2_cfg["model_cfg"],
                ckpt_path=ckpt_path,
                device=self.device,
            )
            self._predictor = SAM2ImagePredictor(sam2_model)
            print(f"[SAM2] Loaded standalone: {ckpt_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to build SAM2 with checkpoint {ckpt_path}: {e}") from e

    def predict_masks_from_boxes(
        self,
        image: Union[Image.Image, np.ndarray],
        boxes: np.ndarray,
        scores: Optional[np.ndarray] = None,
    ) -> list[tuple[np.ndarray, float]]:
        """
        Generate instance masks for each detection box.

        Args:
            image: RGB PIL Image or numpy array
            boxes: np.ndarray of shape (N, 4) with [x1, y1, x2, y2] in pixels
            scores: np.ndarray of shape (N,) with confidence scores

        Returns:
            List of (mask: HxW bool, score: float) tuples
        """
        if self._predictor is None:
            raise RuntimeError("SAM2 model not loaded. Call load() first.")

        if isinstance(image, Image.Image):
            image_np = np.array(image)
        else:
            image_np = image

        # Ensure RGB for SAM2 (RGBA from frontend would cause issues)
        if image_np.ndim == 3 and image_np.shape[2] == 4:
            image_np = image_np[:, :, :3]

        h, w = image_np.shape[:2]
        results = []

        if SAM2_AVAILABLE:
            # ultralytics path — predict(image, bboxes=N_boxes) returns ONE Results object
            # containing ALL N masks (one per box). Each mask corresponds to boxes[j].
            results_list = self._predictor.predict(
                image_np,
                bboxes=boxes.astype(np.float32),
                verbose=False,
            )
            res = results_list[0]
            if res.masks is not None and len(res.masks) > 0:
                mask_arrays = res.masks.data.cpu().numpy()
                for j, mask_np in enumerate(mask_arrays):
                    score_j = scores[j] if scores is not None else 1.0
                    results.append((mask_np.astype(bool), float(score_j)))
            else:
                # Fallback: one box mask per detection
                for i, box in enumerate(boxes):
                    x1, y1, x2, y2 = box.astype(int)
                    fallback = np.zeros((h, w), dtype=bool)
                    fallback[y1:y2, x1:x2] = True
                    score_i = scores[i] if scores is not None else 1.0
                    results.append((fallback, float(score_i)))
        else:
            # Standalone SAM2 path
            self._predictor.set_image(image_np)
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box)
                mask, _ = self._predictor.predict(
                    point_coords=None,
                    point_labels=None,
                    box=np.array([x1, y1, x2, y2]),
                    multimask_output=False,
                )
                score = float(scores[i]) if scores is not None else 1.0
                results.append((mask[0].astype(bool), score))
            self._predictor.reset_image()

        return results

    def predict_automatic_masks(
        self,
        image: Union[Image.Image, np.ndarray],
    ) -> list[dict]:
        """
        Generate masks for all salient objects (no text/detection prompt).
        Uses SAM2's built-in automatic mask generation.
        """
        if self._automatic_generator is None and self._predictor is None:
            raise RuntimeError("SAM2 model not loaded.")

        if isinstance(image, Image.Image):
            image_np = np.array(image)
        else:
            image_np = image

        if self._automatic_generator is not None:
            return self._automatic_generator.generate(image_np)
        else:
            # Use ultralytics automatic — reuse the already-loaded predictor
            results = self._predictor(image_np, verbose=False)
            masks_out = []
            for r in results:
                if r.masks is not None:
                    mask_arrays = r.masks.data.cpu().numpy()
                    for mask_np in mask_arrays:
                        masks_out.append({
                            "segmentation": mask_np.astype(bool),
                            "area": int(mask_np.sum()),
                        })
            return masks_out


# ─── Edge-refinement helpers ──────────────────────────────────────────────────

def _canny_edges(gray: np.ndarray, aperture: int = 3) -> np.ndarray:
    """
    Compute Canny edge map from a grayscale image.

    Args:
        gray: HxW grayscale image, uint8 or float 0-1.
        aperture: Sobel aperture size (3 or 5).

    Returns:
        edges: HxW uint8 binary edge map (0 / 255).
    """
    if gray.dtype != np.uint8:
        gray = (gray * 255).clip(0, 255).astype(np.uint8)
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.2)
    edges = cv2.Canny(blurred, 40, 120, apertureSize=aperture)
    return edges


def refine_mask_edges(
    masks_with_scores: list[tuple[np.ndarray, float]],
    image_rgb: np.ndarray,
    snap_distance: int = 8,
) -> list[tuple[np.ndarray, float]]:
    """
    Refine SAM2 masks by snapping each mask's contour to nearby Canny edges.

    Strategy: for each SAM2 mask, extract its outer contour and march along
    the normal direction from each contour point; if an edge pixel lies within
    `snap_distance` pixels, snap the contour vertex to it.  The result is
    a tighter polygon that follows the object's true boundary.

    Args:
        masks_with_scores: list of (HxW bool mask, score).
        image_rgb: HxWx3 RGB image.
        snap_distance: max distance (px) for edge snapping.

    Returns:
        Refined list of (HxW bool mask, score) in the same order.
    """
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    edges = _canny_edges(gray)

    # Build distance transform from edge pixels — O(1) lookup per point
    edge_pts = np.where(edges > 0)
    if len(edge_pts[0]) == 0:
        return masks_with_scores  # no edges found, return originals

    refined = []
    for mask, score in masks_with_scores:
        # 1. Find external contour of the mask
        mask_u8 = mask.astype(np.uint8)
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            refined.append((mask, score))
            continue

        # Use the largest contour (main object boundary)
        main_contour = max(contours, key=cv2.contourArea)

        # 2. Snap contour points to nearest edge
        snapped_points = main_contour.copy()
        for i in range(len(main_contour)):
            px, py = main_contour[i, 0]

            # Search in a square window [y-snaps..y+snaps]
            y_min = max(0, py - snap_distance)
            y_max = min(edges.shape[0] - 1, py + snap_distance)
            x_min = max(0, px - snap_distance)
            x_max = min(edges.shape[1] - 1, px + snap_distance)

            local_edges = edges[y_min:y_max + 1, x_min:x_max + 1]
            if local_edges.size == 0 or local_edges.max() == 0:
                continue

            # Find nearest edge pixel within the window
            edge_locs = np.argwhere(local_edges > 0)  # (N, 2) in window coords
            if edge_locs.size == 0:
                continue

            # Euclidean distance to each edge pixel
            wx, wy = edge_locs[:, 1], edge_locs[:, 0]  # col, row
            dists = np.sqrt((wx - (px - x_min)) ** 2 + (wy - (py - y_min)) ** 2)
            nearest_idx = np.argmin(dists)
            if dists[nearest_idx] <= snap_distance:
                snapped_points[i, 0, 0] = x_min + wx[nearest_idx]
                snapped_points[i, 0, 1] = y_min + wy[nearest_idx]

        # 3. Re-fill the snapped polygon
        h, w = mask.shape
        new_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(new_mask, [snapped_points], 1)
        refined.append((new_mask.astype(bool), score))

    return refined


def extract_polygon_from_mask(
    mask: np.ndarray,
    simplify_tolerance: float = 1.5,
) -> list[list[float]]:
    """
    Extract the outer contour of a binary mask as a list of normalized polygon points.

    Args:
        mask: HxW bool mask.
        simplify_tolerance: Douglas-Peucker tolerance in pixels for polygon simplification.

    Returns:
        List of [x_norm, y_norm] points (float, 0-1 range) for SVG polygon rendering.
        Returns an empty list if no contour is found.
    """
    mask_u8 = mask.astype(np.uint8)
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []

    # Use the largest contour
    contour = max(contours, key=cv2.contourArea)

    # Simplify polygon to reduce point count while preserving shape fidelity.
    # Use arc-length-relative tolerance to avoid collapsing small contours.
    # Minimum 3 points (triangle) required; skip simplification if perimeter is tiny.
    arc_len = cv2.arcLength(contour, True)
    if len(contour) >= 5 and arc_len > 20:
        epsilon = max(arc_len * 0.002, 0.8)  # relative + floor
        contour = cv2.approxPolyDP(contour, epsilon, True)

    h, w = mask.shape
    return [[float(pt[0][0]) / w, float(pt[0][1]) / h] for pt in contour]

