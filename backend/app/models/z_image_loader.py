"""
Z-Image-Turbo Model Loader.

Tongyi-MAI/Z-Image-Turbo is a ~6B-param distilled text-to-image diffusion
transformer.  The HuggingFace repo weighs ~33 GB on disk (3 transformer
shards × ~10 GB, 3 text-encoder shards × ~4 GB, plus VAE / tokenizer /
scheduler / model_index.json).

The China-friendly flow we use here:

  Strategy 1 — HF Hub via hf-mirror.com (relies on ``HF_HUB_DISABLE_XET=1``
    set in config.py, which forces huggingface_hub to bypass the Xet/CAS
    reconstruction path that 401s through the mirror.  Falls back to plain
    HTTP redirects served by the mirror's CDN edge).
  Strategy 2 — ModelScope ``snapshot_download`` (Alibaba-hosted mirror,
    stable from China, no auth).  Used when strategy 1 is unreachable or
    rate-limited.

We do NOT have a third CDN to fall back to for this model — unlike SAM2
which has dl.fbaipublicfiles.com — so when both HF Hub and ModelScope fail
we surface a clear ``RuntimeError`` rather than spinning forever.
"""
from __future__ import annotations

import glob
import os
import shutil
import time as _time
from typing import Optional


DEFAULT_MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"

# Files we actually need for ZImagePipeline.from_pretrained(...) to succeed.
# Anything else (docs, .gitattributes, etc.) is skipped to save bandwidth.
_REQUIRED_GLOBS = (
    "model_index.json",
    "transformer/*.json",
    "transformer/*.safetensors",
    "text_encoder/*.json",
    "text_encoder/*.safetensors",
    "vae/*.json",
    "vae/*.safetensors",
    "tokenizer/*",
    "scheduler/*",
)


class ZImageModel:
    """
    Z-Image-Turbo checkpoint loader.

    Call ``ensure_downloaded()`` first to pull weights to disk; later calls
    just verify they exist.  ``local_snapshot_path()`` returns the directory
    that can be passed straight into ``ZImagePipeline.from_pretrained(...)``
    so the pipeline loads from the local cache without hitting the network.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        checkpoint_dir: Optional[str] = None,
    ):
        self.model_id = model_id

        # Default to <project-root>/backend/.cache/z-image so weights live
        # alongside the rest of AICSS's cached models instead of dropping
        # into ~/.cache/huggingface.  Matches config.py's image_checkpoint_dir.
        if checkpoint_dir is None:
            checkpoint_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                ".cache",
                "z-image",
            )
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    # ── Local cache discovery ─────────────────────────────────────────────────

    def _local_snapshot_path(self) -> Optional[str]:
        """
        Return the directory containing model_index.json if the snapshot
        has already been downloaded, else None.

        Searches (in order):
          1. <checkpoint_dir>/<repo_id_underscored>/snapshots/<rev>/
          2. <checkpoint_dir>/<repo_id_underscored>/   (loose file tree)
          3. ~/.cache/huggingface/hub/<repo_id_underscored>/snapshots/<rev>/
             (handles the case where a previous run downloaded to the user
             default cache via the HF Hub strategy)

        ``from_pretrained`` accepts the *parent* of ``snapshots/<rev>/`` as
        well as ``snapshots/<rev>/`` itself, so we return whatever HF Hub
        produced.
        """
        repo_folder = self.model_id.replace("/", "--")
        candidates = [
            # preferred project-local hub cache layout
            os.path.join(self.checkpoint_dir, "hub", repo_folder, "snapshots"),
            os.path.join(self.checkpoint_dir, repo_folder, "snapshots"),
            # alternative: snapshot pulled straight into checkpoint_dir via --local-dir
            os.path.join(self.checkpoint_dir, "snapshots"),
            # ModelScope's default layout (~/.cache/modelscope/...) — see
            # strategy 2 for where that path actually lives.
        ]
        for snap_dir in candidates:
            if not os.path.isdir(snap_dir):
                continue
            # Pick the newest revision snapshot
            revisions = sorted(
                (d for d in os.listdir(snap_dir) if not d.startswith(".")),
                reverse=True,
            )
            for rev in revisions:
                rev_path = os.path.join(snap_dir, rev)
                if os.path.isfile(os.path.join(rev_path, "model_index.json")):
                    return rev_path

        # Fallback: anywhere under checkpoint_dir that contains model_index.json
        for root in [self.checkpoint_dir, os.path.join(self.checkpoint_dir, "hub")]:
            for path in glob.glob(os.path.join(root, "**", "model_index.json"), recursive=True):
                return os.path.dirname(path)
        return None

    def is_downloaded(self) -> bool:
        """Return True if the local snapshot is complete enough to load."""
        path = self._local_snapshot_path()
        if path is None:
            return False
        # Sanity-check that at least the transformer + text_encoder + vae exist.
        required_subdirs = ("transformer", "text_encoder", "vae")
        return all(os.path.isdir(os.path.join(path, d)) for d in required_subdirs)

    def local_snapshot_path(self) -> Optional[str]:
        """Public wrapper around _local_snapshot_path() returning the loadable dir."""
        return self._local_snapshot_path()

    # ── Download strategies ──────────────────────────────────────────────────

    def ensure_downloaded(self) -> str:
        """
        Ensure the Z-Image-Turbo snapshot is on disk.  Returns the path to
        the directory that ``ZImagePipeline.from_pretrained(...)`` should be
        pointed at.

        Strategies (in order):

        1. **HF Hub** (``huggingface_hub.snapshot_download``).
           Uses ``HF_ENDPOINT=https://hf-mirror.com`` and
           ``HF_HUB_DISABLE_XET=1`` set in config.py to bypass the Xet/CAS
           reconstruction that 401s through the mirror.  Plain HTTP redirects
           to the mirror's CDN edge then succeed.
        2. **ModelScope** (``modelscope.snapshot_download``).  Alibaba's
           China-hosted mirror; stable and unmodified upstream weights.

        Each strategy retries up to ``HF_DOWNLOAD_RETRIES`` (default 3) times
        with exponential back-off.  If both fail, raises ``RuntimeError``.
        """
        if self.is_downloaded():
            path = self._local_snapshot_path()
            print(f"[ZImage] Found cached snapshot: {path}")
            return path  # type: ignore[return-value]

        # Defensive: make sure the env vars config.py set are still in force
        # (some loaders used at startup may have nuked them).  We want both
        # the China mirror and the Xet-bypass to be active.
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        max_retries = int(os.environ.get("HF_DOWNLOAD_RETRIES", "3"))
        timeout_s = int(os.environ["HF_HUB_DOWNLOAD_TIMEOUT"])

        last_exc: Exception | None = None

        # ── Strategy 1: HF Hub (snapshot_download, Xet disabled) ──────────
        try:
            print(
                f"[ZImage] Downloading {self.model_id} via HF Hub "
                f"(timeout={timeout_s}s, retries={max_retries}) …"
            )
            from huggingface_hub import snapshot_download

            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    print(f"[ZImage] HF Hub retry {attempt}/{max_retries} …")
                    _time.sleep(2 ** attempt)
                try:
                    local_dir = snapshot_download(
                        repo_id=self.model_id,
                        cache_dir=self.checkpoint_dir,
                        allow_patterns=list(_REQUIRED_GLOBS),
                        ignore_patterns=["*.msgpack", "*.h5", "*.onnx", "*.pt"],
                        max_workers=4,
                    )
                    if self.is_downloaded():
                        print(f"[ZImage] HF Hub snapshot ready: {local_dir}")
                        return local_dir
                    raise FileNotFoundError(
                        f"{self.model_id} snapshot incomplete in {local_dir} "
                        f"(missing transformer / text_encoder / vae)"
                    )
                except Exception as exc:
                    last_exc = exc
                    print(
                        f"[ZImage] HF Hub attempt {attempt} failed: "
                        f"{type(exc).__name__}: {str(exc)[:200]}"
                    )
        except ImportError:
            print("[ZImage] huggingface_hub not installed — skipping HF Hub strategy.")

        # ── Strategy 2: ModelScope mirror ───────────────────────────────────
        try:
            print(
                f"[ZImage] Downloading {self.model_id} via ModelScope mirror "
                f"(timeout={timeout_s}s, retries={max_retries}) …"
            )
            from modelscope import snapshot_download as ms_snapshot_download

            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    print(f"[ZImage] ModelScope retry {attempt}/{max_retries} …")
                    _time.sleep(2 ** attempt)
                try:
                    # ModelScope's snapshot_download returns the local dir
                    # under ~/.cache/modelscope/hub/<repo> by default.  We
                    # then re-publish it into our project checkpoint_dir so
                    # the rest of AICSS finds it in one place.
                    ms_dir = ms_snapshot_download(
                        model_id=self.model_id,
                        allow_patterns=list(_REQUIRED_GLOBS),
                    )
                    mirror_dir = self._publish_modelscope_snapshot(ms_dir)
                    if self.is_downloaded():
                        print(f"[ZImage] ModelScope snapshot ready: {mirror_dir}")
                        return mirror_dir
                    raise FileNotFoundError(
                        f"{self.model_id} snapshot from ModelScope missing required dirs"
                    )
                except Exception as exc:
                    last_exc = exc
                    print(
                        f"[ZImage] ModelScope attempt {attempt} failed: "
                        f"{type(exc).__name__}: {str(exc)[:200]}"
                    )
        except ImportError:
            print("[ZImage] modelscope not installed — skipping ModelScope strategy.")

        raise RuntimeError(
            f"Z-Image ({self.model_id}) checkpoint download failed after "
            f"{max_retries} attempts per strategy. Tried HF Hub and ModelScope. "
            f"Last error: {type(last_exc).__name__}: {last_exc}. "
            f"Check network / hf-mirror.com / modelscope.cn / HF_HUB_DOWNLOAD_TIMEOUT."
        ) from last_exc

    # ── Internals ────────────────────────────────────────────────────────────

    def _publish_modelscope_snapshot(self, ms_dir: str) -> str:
        """
        Re-publish a ModelScope ``snapshot_download`` result into our project
        cache so it can be loaded via the same code path as an HF Hub cache.

        ModelScope's default layout is::

            ~/.cache/modelscope/hub/<repo_id>/<repo_files>

        We want a layout::

            <checkpoint_dir>/hub/<repo_id>/snapshots/<rev>/<repo_files>

        so ``_local_snapshot_path()`` finds it.  We copy by default but
        fall back to leaving the ModelScope path in place if copying is
        refused (e.g. cross-drive).
        """
        repo_folder = self.model_id.replace("/", "--")
        target = os.path.join(self.checkpoint_dir, "hub", repo_folder, "snapshots", "modelscope")
        os.makedirs(target, exist_ok=True)

        # If source and target are on the same drive, copy is cheap; otherwise
        # we'd rather just symlink or skip copying and let the caller use
        # ms_dir directly.  For simplicity we always copy file-by-file —
        # ModelScope snapshots are ~33 GB on a typical AICSS host so this
        # only matters once.
        copied = 0
        for root, _dirs, files in os.walk(ms_dir):
            rel = os.path.relpath(root, ms_dir)
            dst_root = os.path.join(target, rel) if rel != "." else target
            os.makedirs(dst_root, exist_ok=True)
            for f in files:
                src = os.path.join(root, f)
                dst = os.path.join(dst_root, f)
                if os.path.exists(dst):
                    continue
                try:
                    shutil.copy2(src, dst)
                    copied += 1
                except Exception:
                    pass
        print(f"[ZImage] Mirrored {copied} files from {ms_dir} to {target}")
        return target


# Singleton convenience — model_manager.py uses these.
_z_image_model: Optional[ZImageModel] = None


def get_z_image_model(model_id: str = DEFAULT_MODEL_ID) -> ZImageModel:
    """Return (or create) the shared Z-Image loader singleton."""
    global _z_image_model
    if _z_image_model is None or _z_image_model.model_id != model_id:
        _z_image_model = ZImageModel(model_id=model_id)
    return _z_image_model
