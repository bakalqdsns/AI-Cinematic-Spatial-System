import sys
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location("demo_pipeline", Path(__file__).parent / "demo_pipeline.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rc = mod.main([
    "--resume", "20260927_055614_旧相册",
    "--output", "scripts/demo_out.mp4",
    "--host", "localhost",
    "--port", "8001",
])
sys.exit(rc)
