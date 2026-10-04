"""
Test script for full script analysis with user's script
"""
import requests
import json
import base64
from pathlib import Path
from datetime import datetime

BASE_URL = "http://localhost:8000/api/aicss/v2/scripts"
OUTPUT_DIR = Path(r"F:\AICinematicSpatialSystem\backend\test_outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

USER_SCRIPT = """
场景1
内景。教室 - 傍晚
画面：
放学后的教室。阳光从西侧的窗户斜射进来，在课桌上投下长长的橙色光斑。大部分座位已经空了，几把椅子倒扣在桌上。
林知夏（17岁，短发，校服，神情安静）独自坐在靠窗倒数第二排的位置。她面前摊着一本数学练习册，
老师的脚步声从走廊经过。林知夏迅速合上练习册。
老师离开后，她重新翻开——翻到了最后一页。
特写：练习册的空白页上，画着一个未完成的漫画肖像——是一个女孩子的半身像，短发、校服，眼睛画得很细致，但嘴和下半张脸只勾了轮廓线，没有完成。
镜头：
她从练习册上抬起头，看向窗外。
窗外天空：
傍晚的天空呈渐变色——近地平线是橘红，往上变成淡紫，再往上是灰蓝。云层稀薄，呈长条状。
异常出现：
林知夏眨了眨眼。
其中一朵云的边缘，出现了一圈均匀的白色描边——大约2毫米宽，像是手工剪纸的轮廓线。描边在云的真实边缘内侧，干净、锐利，没有渐变。
细节：
那朵云的内部纹理也变了。原本蓬松的云气变成了一层一层的薄纸堆叠感，隐约能看到类似手工纸的纤维纹路。
反应：
林知夏皱眉，用力揉眼睛。
她放下手，再看。
恢复正常：
云恢复了正常的云——模糊的边缘，柔软的体积感。白色描边消失。
林知夏盯着窗外看了两秒，慢慢转回头。她拿起笔，在练习册空白处无意识地画了一个纸飞机的简笔画。
镜头推近：
纸飞机涂鸦。
（过渡：笔尖停下。画面渐暗。）

场景2
外景。校园 - 黄昏
时间：同一日，约40分钟后。天色更暗。
画面：
林知夏背着书包，独自穿过校园。周围还有零星的几个学生，都低着头看手机或快步走向校门。
镜头跟拍：她从教学楼侧面走向操场方向。
异常累积：
第一处异常——树：
她经过一棵梧桐树。树干粗壮，树皮斑驳。但当她走到树冠下方时，她抬起头——
树叶的边缘不再是自然的锯齿状，而是变成了平滑的切线。一整片叶子的轮廓像是被剪刀一次剪出的形状，没有任何不规则。
更奇怪的是：风吹过时，树叶没有自然弯曲，而是整片、整体地平移晃动，像一片轻薄的纸。
第二处异常——路灯：
她继续走。路边有一盏老式路灯，铁质灯杆，乳白色球形灯罩。
但从侧面看过去，路灯的灯罩边缘出现了白色切边——灯罩不再是球体，而像是一个被剪出来的圆形纸片，厚度为零。
而且路灯没有投下阴影。它只是亮着，但地面没有任何影子。
第三处异常——教学楼：
林知夏停下脚步。她转头望向刚才走出的教学楼。
教学楼的轮廓——窗框、屋顶的装饰线、外墙的砖缝——全部变成了纸上压痕一样的线条。整栋建筑看起来像是用厚卡纸制作的道具模型。
一阵风吹过。
教学楼的墙面轻微晃动，像一张没有粘牢的纸板在风中颤动。窗户的玻璃出现了折痕——不是裂痕，是纸被折叠后留下的白色折痕线。
周围学生的反应：
两个男生从她身边走过，有说有笑。其中一个几乎撞到她肩膀，但没有看她一眼。
他们也完全没有看向教学楼。
林知夏的表情：
她瞳孔微微放大，嘴唇微张。她的视线快速扫视四周——树、路灯、教学楼、地面（没有影子）、天空（云又出现了描边）。
她攥紧了书包带。
特写：她的指尖用力到发白。
（过渡：她开始向操场方向小跑。镜头跟随。）

场景3
内景/外景。操场角落 - 夜晚
时间：黄昏与黑夜交替时分。天空呈深蓝色。
画面：
林知夏跑到操场最边缘的角落。这里有一面老旧的围墙，墙面上爬满了枯藤。平时没人来。
裂缝：
在围墙与地面的夹角处，空气中出现了一道裂缝。
裂缝大约一米高，最宽处约20厘米，呈不规则形，像撕开的纸边——边缘是毛糙的纤维状，不是平滑的切口。
裂缝内部：
裂缝内部不是黑暗，而是一层层纸张堆叠的纹理。你能看到不同颜色的纸页——米黄的素描纸，白色的打印纸、泛黄的报纸、浅蓝色的便签纸——一层一层交错叠压，像一本巨大书籍被从中间翻开，露出书脊的层理。
音效：
极其微弱的纸张沙沙声，像是有人在远处翻书。
林知夏的动作：
她蹲下来。
她缓慢地伸出右手，手指微微颤抖。
她的指尖触碰到裂缝的边缘。
接触细节：
裂缝在触碰到她手指的瞬间，发出了一声清脆的纸张折叠声——“咔嗒”，像硬卡纸被对折。
特效：
从触碰点开始，裂缝迅速扩大。纸层像翻书一样向两侧翻开，露出一个足以让人钻过去的入口。入口内部透出暖黄色的光——不是电灯那种黄，是旧纸张被岁月浸染的那种米黄色。
林知夏：
她犹豫了不到两秒。
深吸一口气。
低头钻了进去。
画面：
她的身体进入裂缝的瞬间，整个画面像被折叠一样——上下边缘向中间合拢，屏幕变黑半秒。

场景4
内景。纸境 - 开场
画面：
黑屏半秒后，画面从中心向外展开——像打开一张折纸。
全景：
一个完全由纸张构成的世界。
天空：
不是真实天空，而是一块巨大的蓝色手工纸底板，表面有手工纸的粗糙纹理和不均匀的染色。云朵是剪出来的白色卡纸，用透明的丝线悬吊在半空中，丝线一直延伸到看不见的上方。有些云朵微微旋转，像风铃。
太阳：
不是光源，而是一个圆形黄色剪纸，被钉在蓝色纸板上。钉子的金属头清晰可见。阳光没有方向性，整个纸境的光线均匀、柔和，像是被柔光箱打亮的手工模型。
地面：
脚下是由无数层纸铺成的地面——你能看到最上面一层是牛皮纸，边缘翘起，露出下面一层旧报纸，再下面是带横线的笔记本纸。踩上去有轻微的凹陷感，并且发出“沙沙”的声音。
树林：
远处有一片树林。每一棵树都是由绿色卡纸剪出的平面树形，但多层叠加，从正面看有立体感。树干是棕色纸卷成的纸筒。树叶是剪碎的绿色纸片贴在上面。风吹过时（音效：纸张整体的哗啦声），所有树的树叶同时向同一个方向倾斜，像被一只无形的手拨动。
漂浮建筑：
更远处的天空中，漂浮着数十个折叠纸建筑——有的是纸折的教堂，有的是纸折的塔楼，还有一栋看起来像是用作业纸叠成的教学楼。它们没有支撑，悬浮在半空，缓慢自转。
林知夏：
她站在纸境的地面上，张开双臂保持平衡（地面不平，有纸层褶皱）。
她的校服还是原来的样子，但在纸境的光线下，校服的布料边缘也出现了极细的白色描边——她自己也变成了纸境的一部分。
她的表情：
震惊，但不是恐惧。她的眼睛睁大，嘴唇微张，慢慢转了一圈，环顾整个世界。
特写：她的瞳孔里倒映出纸雕天空和悬吊的云朵。

场景5
内景。纸境 - 纸鸟出场
画面：
林知夏停下旋转。她看向不远处的一棵树。
树上：
一棵纸树的顶端枝杈上，停着一只纸鸟。
纸鸟的样子：
纸鸟有真实的体积感（不是扁平剪纸），但它的身体由旧作业纸折叠而成。你能清晰看到作业纸上的蓝色横线、红色批改的勾叉，以及一行铅笔字迹（隐约能辨认出是“林知夏”三个字，被擦过但还有痕迹）。
鸟的翅膀是多层纸叠成的，边缘有细密的剪纸纹路（羽毛形状）。鸟的眼睛是一小片黑色卡纸贴上去的，反光。
鸟的尺寸大约是真实麻雀大小。
动作：
纸鸟歪了歪头（发出轻微的纸张折动声）。然后扑扇翅膀飞了起来——翅膀扇动时发出连续的“啪啪”声，像翻书页。
追逐开始：
纸鸟朝林知夏飞了一圈，然后向树林深处飞去。它飞得不快，像是故意等她。
林知夏：
她几乎没有犹豫，迈步追了上去。
沿途景象（快速蒙太奇）：
揉成团的画稿山丘：
前方出现一座小山丘，高度约三米。
山丘不是土石，而是由数十个揉成球的画稿堆叠而成。能看到露在外面的画纸上有水彩笔画的小人、房子、太阳，都被揉皱了，有些地方颜料晕开。
纸鸟从山丘上方飞过。林知夏爬过去时，脚下踩到一个纸团，纸团滚落，展开一瞬——上面画着一只歪歪扭扭的猫。然后又滚回去合上。
折纸船的天空：
跑过山丘后，头顶上方出现折纸船。
纸船由A4纸折叠而成，尺寸大约半米长，但漂浮在离地两米的高度。不止一艘——有七八艘，大小不一，有的朝上，有的倒扣，缓慢漂浮。
其中一艘船的船底能看出是数学考试卷，红色的“61”清晰可见。
试卷河流：
前方出现一条“河”。
河面是由无数张写满涂改痕迹的试卷连接而成。试卷的白色背景、黑色的印刷字体，红色的批改符号、蓝色的修改文字，构成类似河流的流动感。
试卷之间像传送带一样缓慢向前滑动，发出连续的纸张滑动声。
纸鸟从河面上方飞过。林知夏踩着试卷过河——脚下踩到一张化学试卷，上面有被泪水晕开的痕迹。
被放弃的作品：
经过树林时，大量纸页像落叶般飘过——没完成的漫画、未上色的插画、草稿本中的角色设计、被撕掉的速写。旁边隐约可见字迹：“以后再画”“算了吧”“画不好”。
纸鸟落点：
纸鸟飞过河流，最终落在一座高塔上。

场景6
内景。记忆塔 - 外观到内部
高塔外观：
高塔约十米高，完全由纸页堆叠而成——不是折叠，而是成百上千张纸像砌砖一样一层一层叠放，边缘参差不齐。
纸张种类极其丰富：有笔记本撕下来的活页纸、有便签纸、有打印纸、有素描纸、有彩色手工纸、有信件纸、有包装纸。
有些纸页上写着字，有些是空白的，有些画着画。
风吹过时，所有纸页的边角同时微微翘起、抖动，发出沙沙的白噪音。
进入塔内：
林知夏从底部一个不规则的缺口钻进去。
塔内景象：
内部是空心的，但墙壁由层层叠叠的纸页构成。
大量纸页漂浮在半空中——它们不是被风吹起的，而是像失重一样悬浮，缓慢地上下飘动、自转。
每一页上都是某个人遗忘的东西：
一张泛黄的纸页上，画着一架纸飞机，旁边写着“给爸爸”，字迹稚嫩。
一页被撕成两半又粘起来的信纸上，稚嫩的字迹写着——“我的梦想是成为漫画家。”，日期是三年前。
一页皱巴巴的打印纸上，是一本没完成的漫画，只有两格。
一张照片纸——但照片被烧掉了中间部分，只剩边缘能看到一个人握着铅笔的手臂。
镜头：
林知夏慢慢走过这些漂浮的纸页，目光扫过每一页。她的脚步越来越慢。
关键发现：
她停住。
她面前漂浮着一张纸。
那是一张从速写本上撕下来的纸，边缘是不规则的撕痕。纸张已经泛黄，有折痕和污渍。
纸张内容：
用彩色铅笔画的全家福。
画上有三个人：
左边是父亲，戴眼镜，画着不太像的西装领带，嘴角向上弯成一道弧线。
右边是母亲，长发，穿着红色的裙子（红色铅笔画得很用力，有叠色）。
中间是一个小女孩，扎着两个辫子，张开双臂，笑着。
细节：
这张画被从中间撕成了两半——撕痕正好从女孩的脸部中间穿过，把左半张脸和父亲连在一起，右半张脸和母亲连在一起。
但现在，两半被某种透明的纸胶带（纸境规则）从背面粘合，重新拼成了一整张。撕痕依然可见，像一道伤疤。
林知夏的反应：
她愣住了。
她的嘴唇颤抖。
她伸手，轻轻触碰到纸页的边缘。
闪回（快速）：
一个更年幼的林知夏（大约7岁）哭着撕掉这张画，一下，两下，碎片落在地上。背景里有争吵声（男人的声音、女人的声音，模糊处理）。
然后画面变黑。
回到现在：
林知夏的眼泪无声地流下来。
画中人物的变化（特效）：
纸页上的全家福，原本只是静态的彩色铅笔画。
但在她触碰的瞬间——画中的父亲微微抬起头，母亲转过头，小时候的林知夏眨了眨眼。
他们看向林知夏。
没有对话，只是看着。
林知夏（低声，声音沙哑）：
“……我想起来了。”
"""


def save_b64_image(b64_str: str, filepath: Path):
    """Decode base64 and save to file."""
    if not b64_str:
        return False
    try:
        img_data = base64.b64decode(b64_str)
        filepath.write_bytes(img_data)
        size_kb = len(img_data) / 1024
        print(f"    SAVED {filepath.name} ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        print(f"    ERROR saving {filepath}: {e}")
        return False


# ── Test 1: Parse script ──────────────────────────────────────────────────────
print("=" * 70)
print("TEST 1: Parse Script (剧本解析)")
print("=" * 70)
try:
    response = requests.post(
        f"{BASE_URL}/parse",
        json={"raw_text": USER_SCRIPT, "language": "chinese"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        
        # Save full results
        norm_path = OUTPUT_DIR / f"{timestamp}_full_normalized.txt"
        norm_path.write_text(result.get("normalized_script", ""), encoding="utf-8")
        data_path = OUTPUT_DIR / f"{timestamp}_full_script_data.json"
        data_path.write_text(json.dumps(result.get("script_data", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        
        script_data = result.get("script_data", {})
        scenes = script_data.get("scenes", [])
        characters = script_data.get("characters", [])
        
        print(f"\n  Parsed {len(scenes)} scenes:")
        for i, scene in enumerate(scenes):
            location = scene.get("location", "Unknown")
            time = scene.get("time", "Unknown")
            desc = scene.get("description", "")[:60]
            print(f"    Scene {i+1}: {location} - {time}")
            print(f"      {desc}...")
        
        print(f"\n  Found {len(characters)} characters:")
        for char in characters:
            print(f"    - {char.get('name', 'Unknown')}")
        
        print(f"\n  Saved:")
        print(f"    - {norm_path.name}")
        print(f"    - {data_path.name}")
    else:
        print(f"  Error: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# ── Test 2: Generate character image (林知夏) ────────────────────────────────────
print("\n" + "=" * 70)
print("TEST 2: Generate Character Three-View (林知夏)")
print("=" * 70)
try:
    response = requests.post(
        f"{BASE_URL}/characters/generate-three-view",
        json={
            "character_id": "lin_zhixia",
            "character_name": "林知夏",
            "character_gender": "female",
            "character_personality": "安静、敏感、有艺术天赋，内心渴望表达",
            "project_id": "paper_realm_test"
        }
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"  Visual prompt: {result.get('visual_prompt', '')[:120]}...")
        
        char_dir = OUTPUT_DIR / f"{timestamp}_lin_zhixia"
        char_dir.mkdir(parents=True, exist_ok=True)
        
        for view in ("front", "side", "back"):
            img_b64 = result["three_view_images"].get(view)
            if img_b64:
                save_b64_image(img_b64, char_dir / f"{view}.png")
            else:
                print(f"    {view}: None (generation failed)")
        
        (char_dir / "manifest.json").write_text(
            json.dumps({"character": result.get("character_name"), "visual_prompt": result.get("visual_prompt")}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  Saved to: {char_dir.name}/")
    else:
        print(f"  Error: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# ── Test 3: Generate scene images ──────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST 3: Generate Scene Assets (场景关键帧)")
print("=" * 70)

scenes_to_generate = [
    {
        "scene_id": "scene_classroom",
        "location": "放学后的教室",
        "time": "傍晚",
        "atmosphere": "温暖的橙色夕阳光线，课桌上投下长长的光斑，空旷安静的氛围"
    },
    {
        "scene_id": "scene_campus",
        "location": "校园黄昏",
        "time": "黄昏",
        "atmosphere": "天色渐暗，路灯亮起，教学楼轮廓清晰，梧桐树"
    },
    {
        "scene_id": "scene_paper_realm",
        "location": "纸境世界",
        "time": "永恒黄昏",
        "atmosphere": "由纸张构成的超现实世界，蓝色手工纸天空，剪纸云朵，漂浮建筑"
    },
]

for scene in scenes_to_generate:
    print(f"\n  Generating: {scene['location']}")
    try:
        response = requests.post(
            f"{BASE_URL}/scenes/generate-asset",
            json={
                "scene_id": scene["scene_id"],
                "location": scene["location"],
                "time": scene["time"],
                "atmosphere": scene["atmosphere"],
                "project_id": "paper_realm_test"
            }
        )
        print(f"    Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"    Visual prompt: {result.get('visual_prompt', '')[:100]}...")
            
            scene_dir = OUTPUT_DIR / f"{timestamp}_{scene['scene_id']}"
            scene_dir.mkdir(parents=True, exist_ok=True)
            
            for key in ("wide", "closeup", "mood"):
                img_b64 = result["keyframe_images"].get(key)
                if img_b64:
                    save_b64_image(img_b64, scene_dir / f"{key}.png")
                else:
                    print(f"    {key}: None (generation failed)")
            
            (scene_dir / "manifest.json").write_text(
                json.dumps({"scene": scene["location"], "visual_prompt": result.get("visual_prompt")}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"    Saved to: {scene_dir.name}/")
        else:
            print(f"    Error: {response.text[:300]}")
    except Exception as e:
        print(f"    Error: {e}")

print("\n" + "=" * 70)
print(f"All outputs saved to: {OUTPUT_DIR}")
print("=" * 70)
