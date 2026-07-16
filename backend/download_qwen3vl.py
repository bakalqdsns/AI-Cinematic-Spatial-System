"""Stream-download Qwen3-VL-4B-Instruct safetensors shards from hf-mirror.

This helper bypasses `huggingface_hub`'s default download path because the
current network environment only reaches HuggingFace reliably via the
`hf-mirror.com` mirror, and `huggingface_hub.snapshot_download` hangs there.

Usage:
    python download_qwen3vl.py           # download if not already present
    python download_qwen3vl.py --force   # re-download even if cached

It writes shards to `<repo>/.cache/huggingface/hub/models--Qwen--Qwen3-VL-4B-Instruct/blobs/`
in the format that `transformers.AutoModel.from_pretrained(local_files_only=True)` expects.

Each run is resumable: if a partial shard already exists on disk it will
issue a Range request and append the missing tail.
"""
import os
import sys
import time
import argparse
import requests

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(REPO_DIR, ".cache", "huggingface", "hub")
BLOB_DIR = os.path.join(
    CACHE_DIR, "models--Qwen--Qwen3-VL-4B-Instruct", "blobs"
)
os.makedirs(BLOB_DIR, exist_ok=True)

URLS = [
    (
        "https://hf-mirror.com/Qwen/Qwen3-VL-4B-Instruct/resolve/main/model-00001-of-00002.safetensors",
        4967229296,
    ),
    (
        "https://hf-mirror.com/Qwen/Qwen3-VL-4B-Instruct/resolve/main/model-00002-of-00002.safetensors",
        3908490048,
    ),
]

CHUNK = 2 * 1024 * 1024  # 2 MB
TIMEOUT = 60


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download shards even if they already exist with the expected size.",
    )
    args = parser.parse_args()

    for url, expected in URLS:
        filename = url.rsplit("/", 1)[-1]
        target = os.path.join(BLOB_DIR, filename)
        print(f"\n=== {filename} ({expected / 1e9:.2f} GB) ===", flush=True)

        if not args.force and os.path.exists(target) and os.path.getsize(target) == expected:
            print(f"  Already complete at {target}", flush=True)
            continue

        headers = {}
        existing = 0
        if os.path.exists(target):
            existing = os.path.getsize(target)
            if existing >= expected:
                # Stale oversized file; re-download from scratch
                print(f"  Existing file is larger than expected ({existing} > {expected}); truncating.", flush=True)
                existing = 0
                headers = {}
            else:
                headers["Range"] = f"bytes={existing}-"
                print(f"  Resuming from {existing / 1e6:.1f} MB", flush=True)
        else:
            print(f"  Starting fresh download", flush=True)

        try:
            req = requests.get(url, headers=headers, stream=True, timeout=TIMEOUT)
            req.raise_for_status()
        except Exception as e:
            print(f"  Connection failed: {e}", flush=True)
            print(f"  You can retry later — partial files are kept and resumable.", flush=True)
            continue

        mode = "ab" if existing > 0 else "wb"
        written = existing
        started = time.time()
        last = started

        with open(target, mode, buffering=0) as f:
            for chunk in req.iter_content(chunk_size=CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                now = time.time()
                if now - last >= 5:
                    pct = 100.0 * written / expected
                    speed = (written - existing) / (now - started) / 1e6
                    eta_s = (expected - written) / max(speed * 1e6, 1) if speed > 0 else -1
                    print(
                        f"  [{pct:5.1f}%] {written / 1e9:.2f}/{expected / 1e9:.2f} GB "
                        f"@ {speed:.1f} MB/s, ETA {eta_s / 60:.0f} min",
                        flush=True,
                    )
                    last = now

        elapsed = time.time() - started
        avg = (written - existing) / elapsed / 1e6 if elapsed > 0 else 0
        print(f"  Done in {elapsed:.1f}s ({avg:.1f} MB/s) -> {target}", flush=True)

    # Also download the metadata files (config, tokenizer, etc.) via huggingface_hub
    print("\n=== Fetching metadata files via huggingface_hub ===", flush=True)
    try:
        os.environ.setdefault("HF_HOME", str(os.path.join(REPO_DIR, ".cache", "huggingface")))
        os.environ.setdefault("HF_HUB_CACHE", str(os.path.join(REPO_DIR, ".cache", "huggingface", "hub")))
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id="Qwen/Qwen3-VL-4B-Instruct",
            cache_dir=CACHE_DIR,
            local_files_only=False,
            allow_patterns=[
                "*.json", "*.txt", "*.jinja",
                "preprocessor*", "tokenizer*", "chat_template*",
                "README*",
            ],
        )
        print("  Metadata fetched.", flush=True)
    except Exception as e:
        print(f"  WARNING: metadata fetch failed: {e}", flush=True)

    print("\nAll downloads complete.", flush=True)


if __name__ == "__main__":
    main()