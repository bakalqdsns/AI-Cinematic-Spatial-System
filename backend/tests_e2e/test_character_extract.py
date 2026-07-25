"""
E2E: 调用新版 extract_characters，验证 prompt 重写后仍能正确识别。

输入是混合了真角色 / 假角色（特写/旁白/场景元素）的剧本片段，
期望返回的角色只有真角色。
"""
import asyncio
import json
import sys

sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend")

from app.services.script_parser import extract_characters, ScriptLanguage


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
    print("E2E: extract_characters  (new question-first prompt)")
    print("=" * 70)
    chars = await extract_characters(SAMPLE, ScriptLanguage.CHINESE)
    print(f"返回角色数: {len(chars)}")
    for c in chars:
        print(json.dumps(c.to_dict(), ensure_ascii=False, indent=2))

    # 断言
    names = [c.name for c in chars]
    expected = {"林知夏"}
    forbidden = {"特写", "中景", "异常出现", "内景", "全景", "近景", "远景", "俯拍", "仰拍",
                 "全景", "她的表情", "镜头", "漂浮建筑", "树林", "地面", "云朵", "阳光",
                 "太阳", "天空", "教室", "夜", "黑屏", "音效"}

    missing = expected - set(names)
    leaked = set(names) & forbidden
    print()
    print(f"expected (应有)  : {sorted(expected)}")
    print(f"missing  (遗漏)  : {sorted(missing)}")
    print(f"forbidden (误识) : {sorted(leaked)}")
    print(f"all_names        : {names}")
    if missing or leaked:
        sys.exit(1)
    print("\n[OK] 新 prompt 通过验证")


if __name__ == "__main__":
    asyncio.run(main())
