#!/usr/bin/env python3
"""
CLI: 将 AICSS 项目的某个 shot 打成 Blender 可导入的 ZIP 归档包。

Usage (from backend/):
  python -m scripts.archive_shot --project-id <pid> --shot-id <sid>
  python -m scripts.archive_shot --project-id <pid> --shot-id <sid> --output ./out.zip
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure `app` is importable when run as `python -m scripts.archive_shot`
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive an AICSS shot into a Blender-ready ZIP")
    parser.add_argument("--project-id", required=True, help="Project ID under workspace/projects/")
    parser.add_argument("--shot-id", required=True, help="Shot ID")
    parser.add_argument("--scene-id", default=None, help="Optional scene ID for manifest.sceneId")
    parser.add_argument("--output", "-o", default=None, help="Output ZIP path (default: <project>/archives/...)")
    parser.add_argument("--workspace", default=None, help="Override workspace/projects directory")
    args = parser.parse_args(argv)

    from app.services.shot_archiver import build_shot_archive

    try:
        result = build_shot_archive(
            args.project_id,
            args.shot_id,
            workspace_dir=Path(args.workspace) if args.workspace else None,
            output_path=Path(args.output) if args.output else None,
            scene_id=args.scene_id,
        )
    except FileNotFoundError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[FAIL] archive error: {e}", file=sys.stderr)
        return 1

    print(json.dumps({
        "ok": True,
        "zipPath": result["zipPath"],
        "fileName": result["fileName"],
        "fileSize": result["fileSize"],
        "fileCount": result["fileCount"],
        "projectId": result["projectId"],
        "shotId": result["shotId"],
        "layerCount": len(result["manifest"].get("layers") or {}),
        "meshCount": len(result["manifest"].get("meshes") or []),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
