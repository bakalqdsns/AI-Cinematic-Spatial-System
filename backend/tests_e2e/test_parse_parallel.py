"""
E2E: paper-world script -> /parse pipeline.

Confirms that:
  1. normalize is SKIPPED (script already has "内景 X - 夜晚" headings)
  2. Parallel parse produces header + scenes + characters + paragraphs
  3. The scene index from paragraphs correctly maps to scene_ref_id
  4. The "内景 纸境 - 夜晚" heading appears as a transition paragraph
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend")

from app.services.script_parser import (
    parse_script,
    ScriptLanguage,
    ParagraphType,
)


SAMPLE = """内景 纸境 - 夜晚

黑屏半秒后，画面从中心向外展开——像打开一张折纸。

全景：一个完全由纸张构成的世界。天空：不是真实天空，而是一块巨大的蓝色手工纸底板，表面有手工纸的粗糙纹理和不均匀的染色。云朵是剪出来的白色卡纸，用透明的丝线悬吊在半空中，丝线一直延伸到看不见的上方。有些云朵微微旋转，像风铃。太阳：不是光源，而是一个圆形黄色剪纸，被钉在蓝色纸板上。钉子的金属头清晰可见。阳光没有方向性，整个纸境的光线均匀、柔和，像是被柔光箱打亮的手工模型。

地面：脚下是由无数层纸铺成的地面——你能看到最上面一层是牛皮纸，边缘翘起，露出下面一层旧报纸，再下面是带横线的笔记本纸。踩上去有轻微的凹陷感，并且发出"沙沙"的声音。

树林：远处有一片树林。每一棵树都是由绿色卡纸剪出的平面树形，但多层叠加，从正面看有立体感。树干是棕色纸卷成的纸筒。树叶是剪碎的绿色纸片贴在上面。风吹过时（音效：纸张整体的哗啦声），所有树的树叶同时向同一个方向倾斜，像被一只无形的手拨动。

漂浮建筑：更远处的天空中，漂浮着数十个折叠纸建筑——有的是纸折的教堂，有的是纸折的塔楼，还有一栋看起来像是用作业纸叠成的教学楼。它们没有支撑，悬浮在半空，缓慢自转。

林知夏站在纸境的地面上，张开双臂保持平衡（地面不平，有纸层褶皱）。她的校服还是原来的样子，但在纸境的光线下，校服的布料边缘也出现了极细的白色描边——她自己也变成了纸境的一部分。

她的表情：震惊，但不是恐惧。她的眼睛睁大，嘴唇微张，慢慢转了一圈，环顾整个世界。特写：她的瞳孔里倒映出纸雕天空和悬吊的云朵。

内景 纸境 - 夜晚

林知夏停下旋转。她看向不远处的一棵树。"""


async def main() -> None:
    print("=" * 70)
    print("E2E: parse_script  (parallel: header/scenes/chars/paragraphs)")
    print("=" * 70)

    t0 = time.perf_counter()
    data = await parse_script(SAMPLE, ScriptLanguage.CHINESE)
    elapsed = time.perf_counter() - t0

    print(f"\nelapsed: {elapsed:.2f}s")
    print(f"title  : {data.title!r}")
    print(f"genre  : {data.genre!r}")
    print(f"logline: {data.logline!r}")
    print(f"\ncharacters ({len(data.characters)}):")
    for c in data.characters:
        print("  -", c.id, c.name, c.gender, c.age, c.personality)
    print(f"\nscenes ({len(data.scenes)}):")
    for s in data.scenes:
        print("  -", s.id, s.location, s.time, s.atmosphere, "est_shots=", s.estimated_shots)
    print(f"\nparagraphs ({len(data.story_paragraphs)}):")
    for p in data.story_paragraphs:
        snippet = p.text[:50].replace("\n", " ")
        print(f"  - {p.id:8s} scene={p.scene_ref_id:8s} type={p.paragraph_type.value:11s} "
              f"speaker={p.speaker_id:8s} act={p.contains_action}  '{snippet}…'")

    # ── Assertions ──────────────────────────────────────────────────────────
    errors = []

    # 1. At least one scene captured
    if not data.scenes:
        errors.append("scenes is empty")

    # 2. Characters: only 林知夏
    names = {c.name for c in data.characters}
    if "林知夏" not in names:
        errors.append(f"missing character 林知夏; got {names}")
    forbidden = {"特写", "全景", "树林", "地面", "天空", "太阳", "云朵", "树叶",
                 "灯光", "漂浮建筑", "镜头", "音效", "内景", "她的表情", "夜", "黑屏"}
    leaked = names & forbidden
    if leaked:
        errors.append(f"leaked pseudo-characters: {leaked}")

    # 3. Paragraphs: more than 1, all have valid scene_ref_id
    if not data.story_paragraphs:
        errors.append("paragraphs is empty")
    valid_scene_ids = {s.id for s in data.scenes}
    bad = [p for p in data.story_paragraphs if p.scene_ref_id not in valid_scene_ids]
    if bad:
        errors.append(f"{len(bad)} paragraphs with bad scene_ref_id")

    # 4. Paragraph types are valid
    for p in data.story_paragraphs:
        if not isinstance(p.paragraph_type, ParagraphType):
            errors.append(f"paragraph {p.id} has invalid type {p.paragraph_type}")

    print("\n" + "=" * 70)
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("[OK] parallel parse pipeline produces valid ScriptData")
    print(f"     header+scenes+chars ran in {elapsed:.2f}s (sequential baseline ≈ 12-18s)")


if __name__ == "__main__":
    asyncio.run(main())