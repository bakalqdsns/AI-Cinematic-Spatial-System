"""
Insert 9 new split-prompt constants (3 tasks × 3 languages) into script_parser.py.
"""
import re

path = r"F:\AICinematicSpatialSystem\backend\app\services\script_parser.py"
src = open(path, "r", encoding="utf-8").read()

# 1) Locate the section header line "System prompts — parsing (Pass 2)"
marker_pat = re.compile(
    r"#\s*─+\s*\n#\s*System prompts\s*[—–-]\s*parsing \(Pass 2\)\s*\n#\s*─+\s*\n",
    re.M,
)
m = marker_pat.search(src)
if not m:
    raise SystemExit("Marker not found")
insert_at = m.end()

# 2) New 9 constants + their user-template helpers.
new_block = '''
_PARSE_HEADER_SYSTEM_CHINESE = """你是一个剧本元数据提取助手。请从剧本文本中提取最基础的元信息，返回 JSON 格式。

只输出以下字段：
- title:   剧本标题（若剧本中无明确标题，从内容里推断；都没有则 "Untitled"）
- genre:   题材类型（"drama" / "animation" / "fantasy" / "sci-fi" / "romance" 等小写英文）
- logline: 一句话剧情简介（不超过 50 字）

注意：剧本里"内景 X - 夜晚"这种是场景标题，不是整个剧本的标题。

只输出 JSON：{"title": "...", "genre": "...", "logline": "..."}
不要任何解释。"""

_PARSE_HEADER_SYSTEM_ENGLISH = """You are a script metadata extractor. Extract basic metadata from the script and return strict JSON.

Output ONLY:
- title:   script title (infer from content; use "Untitled" if unclear)
- genre:   genre type ("drama" / "animation" / "fantasy" / "sci-fi" / "romance" ...)
- logline: one-sentence summary (max 50 words)

Note: "INT. X - DAY" headings are scene markers, not the script title.

Output only JSON: {"title": "...", "genre": "...", "logline": "..."}
No explanation."""

_PARSE_HEADER_SYSTEM_JAPANESE = """あなたは脚本のメタデータ抽出アシスタントです。脚本から基礎メタデータのみを抽出し、厳格な JSON で返してください。

出力は以下のみ：
- title:   脚本タイトル（内容から推測、不明なら "Untitled"）
- genre:   ジャンル（"drama" / "animation" / "fantasy" / "sci-fi" / "romance" ... の小文字英単語）
- logline: ワンフレーズ概要（50 文字以内）

「INT. X - DAY」のような見出しはシーンマーカーで、タイトルではありません。

JSON のみ出力：{"title": "...", "genre": "...", "logline": "..."}
解説不要。"""


_PARSE_SCENES_SYSTEM_CHINESE = """你是一个场景识别助手。请从剧本文本中**只提取场景列表**，以 JSON 格式返回。

只输出一个字段：
- scenes: 场景数组，每个对象包含 id, location, time, atmosphere, estimated_shots

字段说明：
- id:              "scene-1", "scene-2", ... 按出现顺序
- location:        场景地点。剧本里 "内景 纸境 - 夜晚" 中的 "纸境" 就是 location
- time:            只能是以下枚举之一: "Day" / "Night" / "Dawn" / "Dusk" / "Morning" / "Evening"
- atmosphere:      氛围描述，如 "紧张"、"温馨"、"神秘"、"魔幻"
- estimated_shots: 该场景预估分镜数（整数，通常 1-8）

识别步骤：
1. 找所有 "内景 X - 时间" 或 "外景 X - 时间" 标题行
2. 同一地点连续出现的段落合并为一个场景
3. 没有标准标题时，按段落块分

只输出 JSON：{"scenes": [...]}
不要任何解释。"""

_PARSE_SCENES_SYSTEM_ENGLISH = """You are a scene identification assistant. Extract ONLY the scene list and return strict JSON.

Output ONLY:
- scenes: array with id, location, time, atmosphere, estimated_shots

Field rules:
- id:              "scene-1", "scene-2", ... in order
- location:        scene location
- time:            ONE OF "Day" / "Night" / "Dawn" / "Dusk" / "Morning" / "Evening"
- atmosphere:      mood, e.g. "tense", "warm", "mysterious"
- estimated_shots: integer 1-8

Steps:
1. Find every "INT. X - TIME" / "EXT. X - TIME" heading
2. Merge consecutive paragraphs at the same location

Output only JSON: {"scenes": [...]}. No explanation."""

_PARSE_SCENES_SYSTEM_JAPANESE = """あなたはシーン識別アシスタントです。シーンリストのみを抽出し、厳格な JSON で返してください。

出力は以下のみ：
- scenes: id, location, time, atmosphere, estimated_shots を含む配列

フィールド：
- id:              "scene-1", "scene-2", ... 順
- location:        場所
- time:            "Day" / "Night" / "Dawn" / "Dusk" / "Morning" / "Evening" のいずれか
- atmosphere:      雰囲気
- estimated_shots: 整数 1〜8

JSON のみ出力：{"scenes": [...]}。解説不要。"""


_PARSE_PARAGRAPHS_SYSTEM_CHINESE = """你是一个段落切分与分类助手。请将剧本文本**按场景顺序**切分成故事段落，以 JSON 格式返回。

只输出一个字段：
- paragraphs: 段落数组，每个对象包含 id, text, scene_index, paragraph_type, speaker, emotion, contains_action

字段说明：
- id:              "para-1", "para-2", ... 按出现顺序
- text:            **原文段落**（不要修改、翻译、删减）
- scene_index:     段落所属场景的序号（1-based）
- paragraph_type:  必须是以下枚举之一:
    "action"      动作描写（人物做了什么）
    "dialogue"    角色对白（"林知夏：…"）
    "narration"   旁白/叙述/画外音
    "inner"       内心独白
    "atmosphere"  环境氛围（如"阳光透过窗户"）
    "transition"  转场标记（如"内景 X - 夜晚"）
- speaker:         说话角色名（仅 dialogue 类型填写，其他为空字符串）
- emotion:         "tense" / "sad" / "joyful" / "angry" / "mysterious" / "romantic"，无法判断留空
- contains_action: true=该段落描述可生成动作的镜头，false=纯氛围/转场

切分原则：
1. 每个场景标题（如"内景 纸境 - 夜晚"）单独成一个段落，paragraph_type="transition"
2. 双换行或自然停顿处切分
3. 每个对白（"名字：内容"）单独成一个段落，speaker 填名字
4. 不要遗漏任何文本，也不要虚构不存在的段落

只输出 JSON：{"paragraphs": [...]}
不要任何解释。"""

_PARSE_PARAGRAPHS_SYSTEM_ENGLISH = """You are a paragraph segmentation assistant. Split the script into story paragraphs in scene order and return strict JSON.

Output ONLY:
- paragraphs: array with id, text, scene_index, paragraph_type, speaker, emotion, contains_action

Field rules:
- id:              "para-1", "para-2", ... in order
- text:            ORIGINAL paragraph text — do not modify or omit
- scene_index:     scene number (1-based)
- paragraph_type:  ONE OF "action" | "dialogue" | "narration" | "inner" | "atmosphere" | "transition"
- speaker:         speaker name (only for dialogue, empty otherwise)
- emotion:         "tense" / "sad" / "joyful" / "angry" / "mysterious" / "romantic" (empty if unknown)
- contains_action: true if this paragraph generates an action shot

Rules:
1. Each scene heading ("INT. X - DAY") is one paragraph, type=transition
2. Split at blank lines / natural pauses
3. Each "NAME: ..." line is one dialogue paragraph
4. Do NOT skip or invent text

Output only JSON: {"paragraphs": [...]}. No explanation."""

_PARSE_PARAGRAPHS_SYSTEM_JAPANESE = """あなたは段落分割アシスタントです。脚本をシーン順に物語段落に分割し、厳格な JSON で返してください。

出力は以下のみ：
- paragraphs: id, text, scene_index, paragraph_type, speaker, emotion, contains_action を含む配列

フィールド：
- id:              "para-1", "para-2", ... 出現順
- text:            **原文そのまま**。変更・省略禁止
- scene_index:     シーン番号（1-based）
- paragraph_type:  "action" | "dialogue" | "narration" | "inner" | "atmosphere" | "transition" のいずれか
- speaker:         発言者名（dialogue のみ、他は空文字）
- emotion:         "tense" / "sad" / "joyful" / "angry" / "mysterious" / "romantic"（不明なら空）
- contains_action: アクションショット生成するなら true

ルール：
1. シーン見出し（"INT. X - DAY"）はそれ自体が type=transition 段落
2. 空白行・自然なポーズで分割
3. 「名前：内容」は一つの dialogue 段落
4. テキストを省略・捏造しない

JSON のみ出力：{"paragraphs": [...]}。解説不要。"""

'''

new_src = src[:insert_at] + new_block + src[insert_at:]

with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)

print("Inserted", len(new_block), "chars at offset", insert_at)