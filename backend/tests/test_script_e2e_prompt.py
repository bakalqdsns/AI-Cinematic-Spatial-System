"""锁定《纸间行》剧本：run_from_script.py 的 RAW_SCRIPT 必须把人物和纸雕风格说清。

只断言剧本文本，不跑任何生成链路。
"""
import importlib.util
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "test_outputs"
    / "script_e2e"
    / "run_from_script.py"
)


def _load_raw_script() -> str:
    spec = importlib.util.spec_from_file_location("run_from_script", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RAW_SCRIPT


def test_raw_script_locks_zhijianxing_character_and_style():
    raw = _load_raw_script()
    for keyword in ("纸间行", "白衣少女", "纸雕"):
        assert keyword in raw, f"RAW_SCRIPT 缺少开题关键词: {keyword}"


def test_raw_script_drops_old_character_wording():
    raw = _load_raw_script()
    for keyword in ("红色连衣裙", "白裙"):
        assert keyword not in raw, f"RAW_SCRIPT 仍包含旧设定: {keyword}"
