"""Locate _PARSE_SYSTEM_ constant blocks in script_parser.py."""
import re

path = r"F:\AICinematicSpatialSystem\backend\app\services\script_parser.py"
src = open(path, "r", encoding="utf-8").read()

for n in ["_PARSE_SYSTEM_CHINESE", "_PARSE_SYSTEM_ENGLISH", "_PARSE_SYSTEM_JAPANESE"]:
    pat = re.compile(r"^" + re.escape(n) + r'\s*=\s*"""(.+?)"""', re.M | re.S)
    m = pat.search(src)
    if m:
        first_line = m.group(1).splitlines()[0]
        print(n, "->", m.span(), "first line:", first_line)
    else:
        print(n, "-> NOT FOUND")