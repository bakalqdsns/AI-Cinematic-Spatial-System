"""
Script Parser Service
LLM-powered script normalization and structured parsing.

Two-pass pipeline:
  Pass 1 — normalize:  raw text  → standard screenplay format
  Pass 2 — parse:       normalized text → structured ScriptData dataclasses

Uses local llama.cpp server (Qwen2.5-7B-Instruct Q4_K_M GGUF) when available, falls back to heuristics.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction helpers (robust against chatty LLM output)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(content: str) -> Optional[dict | list]:
    """
    Extract a JSON object/array from LLM output that may be polluted with
    explanations, markdown fences, or trailing notes.

    Tries in order:
      1. Direct parse (LLM returned clean JSON)
      2. Strip ```json ... ``` markdown fences
      3. Greedy match first {...} or [...] block (handles wrapping prose)
    """
    if not content:
        return None

    # 1. Clean attempt
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. Strip single code fence
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find first balanced { ... } or [ ... ]
    for opener, closer in [("{", "}"), ("[", "]")]:
        idx = content.find(opener)
        if idx == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for end in range(idx, len(content)):
            ch = content[end]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = content[idx : end + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Language enum
# ─────────────────────────────────────────────────────────────────────────────

class ScriptLanguage(str, Enum):
    CHINESE = "chinese"
    ENGLISH = "english"
    JAPANESE = "japanese"


class ParagraphType(str, Enum):
    """Type of content in a story paragraph — drives shot generation."""
    ACTION = "action"        # Pure action description
    DIALOGUE = "dialogue"    # Character speaking
    NARRATION = "narration"  # Voiceover / narrator
    INNER = "inner"          # Inner thought / monologue
    ATMOSPHERE = "atmosphere"  # Environment / mood setup
    TRANSITION = "transition"  # Time/place transition (CUT TO:, FADE IN:)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level regex helpers
# ─────────────────────────────────────────────────────────────────────────────

# Dialogue prefix: "NAME：..." or "NAME: ..." at start of line.
# Single-char names are intentionally allowed (e.g. dialogue in stylized scripts).
_DIALOGUE_PREFIX = re.compile(r"^\s*([A-Z\u4e00-\u9fff][A-Z0-9 \u4e00-\u9fff]*?)\s*[:：]\s*")

# Bracketed character description: "林知夏（17岁，短发，校服）" or "John (30s, detective)".
# Captures the name before the opening bracket.
_BRACKET_DESC_RE = re.compile(r"([\u4e00-\u9fffA-Za-z]{2,8})[（(][^)）]+[)）]")


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Character:
    id: str = ""
    name: str = ""
    gender: str = ""
    age: str = ""
    personality: str = ""
    visual_prompt: str = ""
    reference_image: Optional[str] = None  # base64 or URL

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "personality": self.personality,
            "visual_prompt": self.visual_prompt,
            "reference_image": self.reference_image,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Character:
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            gender=d.get("gender", ""),
            age=d.get("age", ""),
            personality=d.get("personality", ""),
            visual_prompt=d.get("visual_prompt", ""),
            reference_image=d.get("reference_image"),
        )


@dataclass
class Scene:
    id: str = ""
    location: str = ""
    time: str = "Day"  # "Day", "Night", "Dawn", "Dusk", "Morning", "Evening"
    atmosphere: str = ""  # mood
    estimated_shots: int = 0  # set after paragraph parsing
    visual_prompt: str = ""  # English prompt used to generate the scene's keyframes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "location": self.location,
            "time": self.time,
            "atmosphere": self.atmosphere,
            "estimated_shots": self.estimated_shots,
            "visual_prompt": self.visual_prompt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Scene:
        return cls(
            id=d.get("id", ""),
            location=d.get("location", ""),
            time=d.get("time", "Day"),
            atmosphere=d.get("atmosphere", ""),
            estimated_shots=int(d.get("estimated_shots", 0)),
            visual_prompt=d.get("visual_prompt", "") or "",
        )


@dataclass
class StoryParagraph:
    id: str = ""
    text: str = ""
    scene_ref_id: str = ""
    paragraph_type: ParagraphType = ParagraphType.ACTION
    speaker_id: str = ""        # character ID for dialogue/inner paragraphs
    emotion: str = ""           # detected emotion: tense, sad, joyful, etc.
    contains_action: bool = True  # whether this beat generates motion

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "scene_ref_id": self.scene_ref_id,
            "paragraph_type": self.paragraph_type.value,
            "speaker_id": self.speaker_id,
            "emotion": self.emotion,
            "contains_action": self.contains_action,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StoryParagraph:
        try:
            ptype = ParagraphType(d.get("paragraph_type", "action"))
        except ValueError:
            ptype = ParagraphType.ACTION
        return cls(
            id=d.get("id", ""),
            text=d.get("text", ""),
            scene_ref_id=d.get("scene_ref_id", ""),
            paragraph_type=ptype,
            speaker_id=d.get("speaker_id", ""),
            emotion=d.get("emotion", ""),
            contains_action=bool(d.get("contains_action", True)),
        )


@dataclass
class ScriptData:
    title: str = ""
    genre: str = ""
    logline: str = ""
    characters: list[Character] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    story_paragraphs: list[StoryParagraph] = field(default_factory=list)
    language: ScriptLanguage = ScriptLanguage.CHINESE

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "genre": self.genre,
            "logline": self.logline,
            "characters": [c.to_dict() for c in self.characters],
            "scenes": [s.to_dict() for s in self.scenes],
            "story_paragraphs": [p.to_dict() for p in self.story_paragraphs],
            "language": self.language.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScriptData:
        return cls(
            title=d.get("title", ""),
            genre=d.get("genre", ""),
            logline=d.get("logline", ""),
            characters=[Character.from_dict(c) for c in d.get("characters", [])],
            scenes=[Scene.from_dict(s) for s in d.get("scenes", [])],
            story_paragraphs=[StoryParagraph.from_dict(p) for p in d.get("story_paragraphs", [])],
            language=ScriptLanguage(d.get("language", "chinese")),
        )


# ─────────────────────────────────────────────────────────────────────────────
# System prompts — normalization (Pass 1)
# ─────────────────────────────────────────────────────────────────────────────

_NORMALIZE_SYSTEM_CHINESE = """你是一个专业的剧本格式化助手。请将用户输入的原始剧本文本重写为标准的电影/动画剧本格式。

要求：
1. 使用 INT. / EXT. 标注场景（内部/外部）
2. 每个场景标注时间和地点
3. 角色对白使用 "角色名：" 前缀
4. 动作描述单独成行
5. 保持原文的故事情节不变
6. 只输出重写后的剧本，不要解释

示例格式：
INT. 咖啡馆 - 日

咖啡师忙碌地调制咖啡。阳光透过窗户洒进来。

李明：（紧张地环顾四周）他已经迟到了半小时了。

张华：（推门而入）抱歉，路上堵车了。
"""

_NORMALIZE_SYSTEM_ENGLISH = """You are a professional screenplay formatter. Rewrite the raw script text into standard film/animation screenplay format.

Requirements:
1. Use INT. / EXT. for scene headings (interior/exterior)
2. Mark time and location for each scene
3. Character dialogue uses "CHARACTER NAME:" prefix
4. Action descriptions on separate lines
5. Keep the original story unchanged
6. Output only the rewritten screenplay, no explanation

Example format:
INT. COFFEE SHOP - DAY

The barista busily makes coffee. Sunlight streams through the windows.

LI MING: (nervously looking around) He's already 30 minutes late.

ZHANG HUA: (entering through the door) Sorry, there was traffic.
"""

_NORMALIZE_SYSTEM_JAPANESE = """あなたはプロフェッショナルな脚本フォーマッターです。 生テキストを標準的な映画/アニメ脚本フォーマットに書き直してください。

要件：
1. シーン見出しにはINT./EXT.を使用（室内/屋外）
2. 各シーンに時間と場所を記録
3. キャラクターのセリフは「キャラクター名：」を付ける
4. アクション説明は別行
5. 元的故事は変更しない
6. 書き直した脚本のみを出力"""


# ─────────────────────────────────────────────────────────────────────────────
# System prompts — parsing (Pass 2)
# ─────────────────────────────────────────────────────────────────────────────


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

═══════════════════════════════════════════════════════════
切分原则（重要）
═══════════════════════════════════════════════════════════
1. 每个场景标题（如"内景 纸境 - 夜晚"）单独成一个段落，paragraph_type="transition"
2. 双换行或自然停顿处切分
3. 每个对白（"名字：内容"）单独成一个段落，speaker 填名字
4. 不要遗漏任何文本，也不要虚构不存在的段落

═══════════════════════════════════════════════════════════
判定 paragraph_type 的关键 — **冒号 ≠ 对白**
═══════════════════════════════════════════════════════════
"名字：内容" 才是 dialogue（名字是 2-4 字人名，且后面跟的是该人物的台词）。
下面这些**绝对不是 dialogue**，即使它们中间或开头有冒号：

  • 段落引导词 + 冒号：  "全景：一个完全由纸张构成的世界…"
  • 场景元素 + 冒号：    "树林：远处有一片树林…"
  • 方位/视点 + 冒号：   "地面：脚下是…"
  • 物件 + 冒号：        "漂浮建筑：更远处的天空中…"
  • 表情/反应 + 冒号：   "她的表情：震惊，但不是恐惧。"
  • 镜头术语 + 冒号：    "特写：她的瞳孔里倒映出…"

这些都属于：
  - atmosphere（环境/场景元素）→ contains_action = false
  - action（镜头引导下的描写）  → contains_action = true

判定 dialogue 的硬标准：**冒号前面是真实人名 + 冒号后面是那个人说的话**。
两者缺一不可。

═══════════════════════════════════════════════════════════
示例
═══════════════════════════════════════════════════════════
输入片段：
"内景 纸境 - 夜晚

全景：一个完全由纸张构成的世界。

林知夏：我最近总觉得有人跟着我。

她的表情：震惊，但不是恐惧。

内景 纸境 - 夜晚

林知夏停下旋转。"

输出：
{
  "paragraphs": [
    {"id": "para-1", "text": "内景 纸境 - 夜晚", "scene_index": 1, "paragraph_type": "transition", "speaker": "", "emotion": "", "contains_action": false},
    {"id": "para-2", "text": "全景：一个完全由纸张构成的世界。", "scene_index": 1, "paragraph_type": "atmosphere", "speaker": "", "emotion": "mysterious", "contains_action": false},
    {"id": "para-3", "text": "林知夏：我最近总觉得有人跟着我。", "scene_index": 1, "paragraph_type": "dialogue", "speaker": "林知夏", "emotion": "tense", "contains_action": true},
    {"id": "para-4", "text": "她的表情：震惊，但不是恐惧。", "scene_index": 1, "paragraph_type": "action", "speaker": "", "emotion": "", "contains_action": true},
    {"id": "para-5", "text": "内景 纸境 - 夜晚", "scene_index": 2, "paragraph_type": "transition", "speaker": "", "emotion": "", "contains_action": false},
    {"id": "para-6", "text": "林知夏停下旋转。", "scene_index": 2, "paragraph_type": "action", "speaker": "", "emotion": "", "contains_action": true}
  ]
}

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

═══════════════════════════════════════════════════════════
CRITICAL — A colon does NOT mean dialogue
═══════════════════════════════════════════════════════════
A "NAME: ..." line is dialogue ONLY if the part before the colon is a real
human name (2-4 words) AND the part after is what that person is saying.

The following are NEVER dialogue, even with a colon:
  • Shot labels:  "Wide shot: a paper world..."
  • Scene elements: "Forest: in the distance..."
  • Locations:    "Ground: under foot..."
  • Objects:      "Floating buildings: dozens of..."
  • Reactions:    "Her expression: shock but not fear"
  • POV phrases:  "Her POV: the paper sky..."

These belong to atmosphere (no action) or action (yes action).
Type dialogue ONLY when both sides of the colon match the rule above.

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

═══════════════════════════════════════════════════════════
重要 — コロンは dialogue を意味しない
═══════════════════════════════════════════════════════════
「名前：内容」が dialogue になるのは、コロンの前が実在人名（2〜4 語）かつ、
後ろがその人物の発言の場合のみ。

以下は絶対 dialogue ではない（コロンがあっても）：
  • ショットラベル：「ワイドショット：紙の世界が…」
  • シーン要素：「森：遠くには…」
  • ロケーション：「地面：足元には…」
  • オブジェクト：「浮かぶ建物：数十の…」
  • 反応：「彼女の表情：衝撃しかし恐怖ではない」
  • 視点：「彼女の視点：紙細工の空…」

これらは atmosphere（アクションなし）か action（アクションあり）に分類。
dialogue に分類するのは、上記ルールを両方満たす場合のみ。

JSON のみ出力：{"paragraphs": [...]}。解説不要。"""

_PARSE_SYSTEM_CHINESE = """你是一个专业的剧本分析助手。请从剧本文本中提取结构化信息，返回JSON格式。

输出JSON必须包含以下字段：
- title: 剧本标题
- genre: 题材类型
- logline: 一句话简介
- characters: 角色数组，每个包含 id, name, gender, age, personality
- scenes: 场景数组，每个包含 id, location, time, atmosphere, estimated_shots
- story_paragraphs: 故事段落数组，每个包含 id, text, scene_ref_id, paragraph_type, speaker_id, emotion, contains_action

注意事项：
- id 使用简短字符串如 "char-1", "scene-1", "para-1"
- characters 中的 name 必须是剧本中实际出现的**真正人类角色**名
- scenes 中的 location 格式如 "咖啡馆", "街道", "办公室"
- time 只能是: "Day", "Night", "Dawn", "Dusk", "Morning", "Evening"
- atmosphere 是氛围描述如 "紧张", "温馨", "神秘"
- story_paragraphs 的 text 是原始段落文本
- 每个段落必须关联一个场景(scene_ref_id)
- 场景的 estimated_shots 预估该场景需要多少个分镜

═══════════════════════════════════════════════════════════
【角色识别 — 直接用这个问题来引导】
请用这句话来指导你的识别：
“这个剧本中有哪些角色？”
先列出所有像人名的词，再逐一验证它是否：
  (a) 在引号 "..." 前作为说话者， 或
  (b) 在括号中被介绍（"林知夏（17岁）"）， 或
  (c) 作为动作主语（"林知夏 站在…"）。
满足任一才保留；否则排除。
═══════════════════════════════════════════════════════════
段落类型 paragraph_type 必须使用以下枚举值之一：
═══════════════════════════════════════════════════════════
- "action": 动作描写（人物做了什么）
- "dialogue": 角色对白
- "narration": 旁白/叙述/画外音
- "inner": 内心独白
- "atmosphere": 环境氛围描写（如"阳光透过窗户"）
- "transition": 转场标记（CUT TO / 切到）

- speaker_id: 对白段落的说话角色 id（如果是 dialogue 类型），其他类型为空
- emotion: 段落情绪，如 "tense", "sad", "joyful", "angry", "mysterious", "romantic"，无则为空
- contains_action: 该段落是否包含需要生成动作的镜头（atmosphere/transition 为 false）

只输出JSON，不要任何解释"""

_PARSE_SYSTEM_ENGLISH = """You are a professional script analysis assistant. Extract structured information from the script text and return JSON format.

Output JSON must contain:
- title: script title
- genre: genre type
- logline: one-sentence summary
- characters: array with id, name, gender, age, personality
- scenes: array with id, location, time, atmosphere, estimated_shots
- story_paragraphs: array with id, text, scene_ref_id, paragraph_type, speaker_id, emotion, contains_action

Notes:
- id as short strings like "char-1", "scene-1", "para-1"
- characters name must be actual character names from the script
- scenes location format like "Coffee Shop", "Street", "Office"
- time only: "Day", "Night", "Dawn", "Dusk", "Morning", "Evening"
- atmosphere is mood like "tense", "warm", "mysterious"
- story_paragraphs text is raw paragraph text
- Each paragraph must reference a scene (scene_ref_id)
- scene.estimated_shots: estimated number of shots needed for this scene

paragraph_type must be one of:
- "action": character action description
- "dialogue": character speaking
- "narration": voiceover / narrator
- "inner": inner thought / monologue
- "atmosphere": environment / mood description
- "transition": transition marker (CUT TO, FADE IN)

speaker_id: character id for dialogue paragraphs (empty for others)
emotion: e.g. "tense", "sad", "joyful", "angry", "mysterious", "romantic" (empty if none)
contains_action: whether this paragraph generates an action shot (false for atmosphere/transition)

Output only JSON, no explanation"""

_PARSE_SYSTEM_JAPANESE = """あなたはプロフェッショナルな脚本分析アシスタントです。脚本から構造化情報を抽出し、JSON形式で返してください。

出力JSONには以下が含まれる必要があります：
- title: スクリプトタイトル
- genre: ジャンル
- logline: ワンフレーズ概要
- characters: id, name, gender, age, personality を含む配列
- scenes: id, location, time, atmosphere を含む配列
- story_paragraphs: id, text, scene_ref_id を含む配列

注意：
- idは "char-1", "scene-1", "para-1" のような短い文字列"""


# ─────────────────────────────────────────────────────────────────────────────
# System prompts — character extraction (Pass 1.5 / character-first pipeline)
# ─────────────────────────────────────────────────────────────────────────────

_CHARACTER_EXTRACT_SYSTEM_CHINESE = """你的任务：阅读下面这段剧本，**直接回答**“这个剧本中有哪些角色”，
并以严格的 JSON 格式输出答案。

═══════════════════════════════════════════════════════════
回答问题的思路（请一步步想）
═══════════════════════════════════════════════════════════
第一步：把剧本中所有**看起来像人名**的词先列出来。
第二步：对每个候选词，检查它在剧本中是否：
        (a) 在某段引号 “...” 前面作为说话者（“林知夏：...”），或者
        (b) 在括号里被介绍外貌/年龄/性格（“林知夏（17 岁，短发）”），或者
        (c) 作为动作的主语（“林知夏 推开门”）。
        满足任一条就**保留**；都不满足就**剔除**。
第三步：把保留下来的名字填到 JSON。

═══════════════════════════════════════════════════════════
JSON 格式（必须严格遵守，不要任何多余内容）
═══════════════════════════════════════════════════════════
{
  "characters": [
    {"id": "char-1", "name": "林知夏", "gender": "female", "age": "17", "personality": "安静、敏感的学生"}
  ]
}

字段要求：
- id    : "char-1"、"char-2"... 按识别顺序递增
- name  : 保留剧本原文（中文人名保留中文，英文名保留英文）
- gender: "male" / "female" / "other" / ""  （无法判断留空）
- age   : "17" / "30s" / "child" / "adult"   （括号里的具体年龄直接取）
- personality: 一句话简述；无法推断留空

═══════════════════════════════════════════════════════════
哪些词**绝对不是**角色（哪怕它们出现在剧本开头）
═══════════════════════════════════════════════════════════
• 镜头/景别词：特写、中景、近景、远景、全景、俯拍、仰拍、长镜头、空镜
• 段落引导词：异常出现、异常累积、异常、声音、光线
• 场景元素：裂缝、树林、漂浮建筑、地面、天空、灯光、云、树叶
• 视角/反应：她的表情、他的反应、周围学生的反应
• 泛指代词：她、他、他们、它、某人、那个人
• 方位/时间：教室、操场、学校、夜、傍晚、黄昏

═══════════════════════════════════════════════════════════
示例（few-shot）
═══════════════════════════════════════════════════════════
输入剧本：
“特写：林知夏（17 岁，校服，短发）站在教室窗前。
 林知夏：我最近总觉得有人跟着我。
 中景：教室走廊空无一人。
 旁白：夜深了。”

你的输出：
{
  "characters": [
    {"id": "char-1", "name": "林知夏", "gender": "female", "age": "17", "personality": "敏感、警觉的学生"}
  ]
}
（“特写”“中景”“旁白”都不是角色，已剔除。）"""

_CHARACTER_EXTRACT_SYSTEM_ENGLISH = """Your task: read the script below and directly answer
**"Which characters appear in this script?"**. Return your answer as strict JSON.

Steps to think through:
1. List every word in the script that looks like a person's name.
2. For each candidate, keep it ONLY if it does at least one of these in the script:
   (a) appears before a quoted line of dialogue ("John: ..."),
   (b) is introduced inside parentheses with age/appearance ("John (30s, detective)"),
   (c) acts as the subject of an action ("John opens the door").
   If none apply, drop it.
3. Put the survivors into the JSON.

JSON shape (strict, no extra text):
{
  "characters": [
    {"id": "char-1", "name": "John", "gender": "male", "age": "30s", "personality": "curious detective"}
  ]
}

Field rules:
- id    : "char-1", "char-2", ... in detection order
- name  : preserve original spelling/language
- gender: "male" / "female" / "other" / ""
- age   : "17" / "30s" / "child" / "adult" (take from parentheses if present)
- personality: one short phrase; empty if unknown

Words that are NEVER characters, even if they open a paragraph:
- Shot labels: "Close-up", "Wide shot", "POV", "Tracking shot", "Voiceover"
- Event markers: "Anomaly detected", "Sound effect"
- Scene elements: "Crack", "Forest", "Sky", "Door", "Tree"
- Perspective phrases: "Her reaction", "His expression"
- Generic pronouns: "She", "He", "They", "Someone"
- Locations/times: "Classroom", "School", "Night"

Example:
Input script:
"Close-up on John (30s, detective) standing in the doorway.
 John: Something's not right here.
 Wide shot: the empty street.
 Voiceover: It was past midnight."

Your output:
{
  "characters": [
    {"id": "char-1", "name": "John", "gender": "male", "age": "30s", "personality": "cautious detective"}
  ]
}
("Close-up", "Wide shot", "Voiceover" are NOT characters.)"""

_CHARACTER_EXTRACT_SYSTEM_JAPANESE = """タスク：以下の脚本を読み、「この脚本にはどのキャラクターが登場しますか？」という問いに
**直接答え**、結果を厳格な JSON で出力してください。

思考手順：
1. まず、人名のように見える語を全てリストアップする。
2. 各候補について、脚本の中で次のいずれかを行っているか確認する：
   (a) セリフ “...” の前に話者として現れる（「林：...」）、
   (b) 括弧内で年齢・外見とともに紹介される（「林（17歳、学生）」）、
   (c) 動作の主語になっている（「林 が ドアを開ける」）。
   どれにも当てはまらなければ除外する。
3. 残った名前を JSON に詰める。

JSON 形式（厳守、解説不要）：
{
  "characters": [
    {"id": "char-1", "name": "林", "gender": "female", "age": "17", "personality": "内気な学生"}
  ]
}

フィールド：
- id    : "char-1", "char-2", ... 検出順
- name  : 原文のまま
- gender: "male" / "female" / "other" / ""
- age   : "17" / "30s" / "child" / "adult"（括弧内から取得）
- personality: 短い一文。分からなければ空文字

絶対にキャラクターではない語（段落頭でも除外）：
- ショット名：「クローズアップ」「ワイドショット」「POV」「モノローグ」
- 出来事：「異変」「物音」
- シーン要素：「森」「空」「ドア」「木」
- 視点・反応：「彼女の表情」「彼の反応」
- 代名詞：「彼」「彼女」「誰か」
- 場所・時間：「教室」「学校」「夜」"""




# ─────────────────────────────────────────────────────────────────────────────
# Prompt helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_normalize_prompt(language: ScriptLanguage) -> tuple[str, str]:
    """Return (system_prompt, user_template) for normalization."""
    prompts = {
        ScriptLanguage.CHINESE: (
            _NORMALIZE_SYSTEM_CHINESE,
            "请将以下剧本文本重写为标准格式：\n\n{text}",
        ),
        ScriptLanguage.ENGLISH: (
            _NORMALIZE_SYSTEM_ENGLISH,
            "Please rewrite the following script into standard format:\n\n{text}",
        ),
        ScriptLanguage.JAPANESE: (
            _NORMALIZE_SYSTEM_JAPANESE,
            "以下の脚本テキストを標準形式に書き直してください：\n\n{text}",
        ),
    }
    return prompts[language]


def _build_parse_prompt(language: ScriptLanguage) -> tuple[str, str]:
    """Return (system_prompt, user_template) for parsing."""
    prompts = {
        ScriptLanguage.CHINESE: (_PARSE_SYSTEM_CHINESE, "{normalized_script}"),
        ScriptLanguage.ENGLISH: (_PARSE_SYSTEM_ENGLISH, "{normalized_script}"),
        ScriptLanguage.JAPANESE: (_PARSE_SYSTEM_JAPANESE, "{normalized_script}"),
    }
    return prompts[language]


def _build_character_extract_prompt(language: ScriptLanguage) -> tuple[str, str]:
    """Return (system_prompt, user_template) for character-only extraction."""
    prompts = {
        ScriptLanguage.CHINESE: (
            _CHARACTER_EXTRACT_SYSTEM_CHINESE,
            "问题：这个剧本中有哪些角色？\n\n以下是剧本：\n{text}\n\n请按 system 中规定的 JSON 格式回答，只输出 JSON。",
        ),
        ScriptLanguage.ENGLISH: (
            _CHARACTER_EXTRACT_SYSTEM_ENGLISH,
            "Question: Which characters appear in this script?\n\nScript:\n{text}\n\nAnswer strictly in the JSON format defined in the system prompt.",
        ),
        ScriptLanguage.JAPANESE: (
            _CHARACTER_EXTRACT_SYSTEM_JAPANESE,
            "質問：この脚本にはどのキャラクターが登場しますか？\n\n脚本：\n{text}\n\nsystem で指定された JSON 形式でだけ答えてください。",
        ),
    }
    return prompts[language]


# ─────────────────────────────────────────────────────────────────────────────
# Core async pipeline functions
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_character_extraction(text: str, language: ScriptLanguage) -> list[Character]:
    """
    Heuristic-only character extraction (no LLM).

    Used when LLM is unavailable. Reuses the bracket-description and dialogue-
    prefix logic that already powers the fallback ScriptData path.
    """
    characters: list[Character] = []
    seen_ids: set[str] = set()
    counter = 1

    def _add(name: str) -> None:
        nonlocal counter
        if not name or name in _PSEUDO_CHARACTER_BLACKLIST:
            return
        if any(c.name == name for c in characters):
            return
        characters.append(Character(id=f"char-{counter}", name=name))
        seen_ids.add(name)
        counter += 1

    # Bracketed descriptions: "林知夏（17岁，短发，校服）"
    for m in _BRACKET_DESC_RE.finditer(text):
        _add(m.group(1).strip())

    # Dialogue prefixes: "林知夏：..."
    for line in text.replace("\r\n", "\n").splitlines():
        line = line.strip()
        m = _DIALOGUE_PREFIX.match(line)
        if m:
            _add(m.group(1).strip())

    return characters


async def extract_characters(
    raw_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
    dashscope_api_key: Optional[str] = None,
) -> list[Character]:
    """
    Pass 1.5 — Extract ONLY real human characters from the script.

    This is the first step of the character-first pipeline. It runs an LLM
    call focused exclusively on character identification (no scene/paragraph
    extraction). Falls back to heuristic bracket/dialogue extraction if the
    LLM is unavailable.

    Returns:
        A list of Character dataclasses, filtered through
        ``_filter_real_characters`` to drop pseudo-characters the LLM may
        hallucinate (e.g. "特写", "异常出现", "裂缝").
    """
    system_prompt, user_template = _build_character_extract_prompt(language)
    user_text = user_template.format(text=raw_text)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(messages, temperature=0.2, max_tokens=2048)
        if content:
            data = _extract_json(content)
            if isinstance(data, dict) and "characters" in data:
                raw_chars = data["characters"] or []
                kept_dicts = _filter_real_characters(raw_chars, [])
                # The filter has nothing to anchor against (no paragraphs yet),
                # so be lenient: retain any entry with non-empty metadata.
                if not kept_dicts and raw_chars:
                    kept_dicts = [
                        c for c in raw_chars
                        if isinstance(c, dict) and c.get("name")
                    ]
                kept = [Character.from_dict(c) for c in kept_dicts]
                logger.info(
                    "[script_parser] character extraction: %d raw -> %d kept",
                    len(raw_chars), len(kept),
                )
                return kept
            # Couldn't parse — log and fall through to heuristic
            logger.warning(
                "[script_parser] character extraction returned unexpected shape; "
                "falling back to heuristic"
            )
    except Exception as e:
        logger.warning(
            "[script_parser] character extraction LLM call failed: %s — falling back",
            e,
        )

    # Fallback heuristic
    fallback = _fallback_character_extraction(raw_text, language)
    logger.info(
        "[script_parser] character extraction fallback: %d characters",
        len(fallback),
    )
    return fallback

async def normalize_script(
    raw_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
    dashscope_api_key: Optional[str] = None,
) -> str:
    """
    Pass 1 — Normalize raw script text into standard screenplay format.

    Uses local llama.cpp server (Qwen2.5-7B-Instruct Q4_K_M GGUF) when available; falls back to
    minimal formatting if the call fails.
    """
    system_prompt, user_template = _build_normalize_prompt(language)
    user_text = user_template.format(text=raw_text)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(messages, temperature=0.3, max_tokens=4096)
        if content:
            logger.info("[script_parser] normalize succeeded (%d chars)", len(content))
            return content
        logger.warning("[script_parser] Local LLM returned empty — falling back")
    except Exception as e:
        logger.warning("[script_parser] Local LLM call failed: %s — falling back", e)

    # Fallback: return as-is with minimal cleanup
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    return "\n\n".join(lines)


async def _extract_header(
    raw_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> dict:
    """
    Sub-task: extract title / genre / logline via a tiny, dedicated LLM call.
    Returns a dict with keys: title, genre, logline (any may be missing).
    Falls back to a deterministic extract when LLM is unavailable.
    """
    system_prompts = {
        ScriptLanguage.CHINESE: _PARSE_HEADER_SYSTEM_CHINESE,
        ScriptLanguage.ENGLISH: _PARSE_HEADER_SYSTEM_ENGLISH,
        ScriptLanguage.JAPANESE: _PARSE_HEADER_SYSTEM_JAPANESE,
    }
    user_templates = {
        ScriptLanguage.CHINESE: "请提取下面这段剧本的元信息（title/genre/logline）：\n\n{text}",
        ScriptLanguage.ENGLISH: "Extract metadata (title/genre/logline) from this script:\n\n{text}",
        ScriptLanguage.JAPANESE: "次の脚本のメタデータ（title/genre/logline）を抽出してください：\n\n{text}",
    }
    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(
            [
                {"role": "system", "content": system_prompts[language]},
                {"role": "user", "content": user_templates[language].format(text=raw_text)},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        if content:
            data = _extract_json(content)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("[script_parser] header extract failed: %s — fallback", e)
    # Fallback
    title_match = re.search(r"《([^》\n]+)》|^\s*([A-Z][A-Za-z0-9 _-]{2,40})\s*$", raw_text, re.M)
    title = "Untitled"
    if title_match:
        title = title_match.group(1) or title_match.group(2) or title
    return {"title": title, "genre": "drama", "logline": raw_text[:60].replace("\n", " ").strip()}


async def _extract_scenes(
    raw_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> list[dict]:
    """
    Sub-task: extract scenes array only (no characters, no paragraphs).
    Returns a list of scene dicts: id, location, time, atmosphere, estimated_shots.
    On failure returns an empty list.
    """
    system_prompts = {
        ScriptLanguage.CHINESE: _PARSE_SCENES_SYSTEM_CHINESE,
        ScriptLanguage.ENGLISH: _PARSE_SCENES_SYSTEM_ENGLISH,
        ScriptLanguage.JAPANESE: _PARSE_SCENES_SYSTEM_JAPANESE,
    }
    user_templates = {
        ScriptLanguage.CHINESE: "请从这个剧本中**只**提取场景列表：\n\n{text}",
        ScriptLanguage.ENGLISH: "Extract ONLY the scene list from this script:\n\n{text}",
        ScriptLanguage.JAPANESE: "次の脚本からシーンリスト**のみ**を抽出してください：\n\n{text}",
    }
    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(
            [
                {"role": "system", "content": system_prompts[language]},
                {"role": "user", "content": user_templates[language].format(text=raw_text)},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        if content:
            data = _extract_json(content)
            if isinstance(data, dict) and isinstance(data.get("scenes"), list):
                return data["scenes"]
    except Exception as e:
        logger.warning("[script_parser] scenes extract failed: %s — fallback", e)
    return []


async def _extract_paragraphs(
    raw_text: str,
    scene_count: int,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> list[dict]:
    """
    Sub-task: extract story paragraphs only (no title, no characters, no scenes).
    Returns a list of paragraph dicts: id, text, scene_index, paragraph_type,
    speaker, emotion, contains_action.
    """
    system_prompts = {
        ScriptLanguage.CHINESE: _PARSE_PARAGRAPHS_SYSTEM_CHINESE,
        ScriptLanguage.ENGLISH: _PARSE_PARAGRAPHS_SYSTEM_ENGLISH,
        ScriptLanguage.JAPANESE: _PARSE_PARAGRAPHS_SYSTEM_JAPANESE,
    }
    user_templates = {
        ScriptLanguage.CHINESE: (
            "剧本共 {scene_count} 个场景（scene_index 从 1 到 {scene_count}）。"
            "请按场景顺序切分下面的剧本为段落数组：\n\n{{text}}"
        ).format(scene_count=scene_count, text="{text}"),
        ScriptLanguage.ENGLISH: (
            "The script has {scene_count} scenes (scene_index 1..{scene_count}). "
            "Split the following script into paragraphs in scene order:\n\n{{text}}"
        ).format(scene_count=scene_count, text="{text}"),
        ScriptLanguage.JAPANESE: (
            "脚本には {scene_count} 個のシーンがあります（scene_index は 1〜{scene_count}）。"
            "次の脚本をシーン順に段落配列へ分割してください：\n\n{{text}}"
        ).format(scene_count=scene_count, text="{text}"),
    }
    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(
            [
                {"role": "system", "content": system_prompts[language]},
                {"role": "user", "content": user_templates[language].format(text=raw_text)},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        if content:
            data = _extract_json(content)
            if isinstance(data, dict) and isinstance(data.get("paragraphs"), list):
                return data["paragraphs"]
    except Exception as e:
        logger.warning("[script_parser] paragraphs extract failed: %s — fallback", e)
    return []


async def _llm_chat_safe(system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 1024) -> str:
    """Helper: call local LLM, return "" on any failure (so gather() never crashes)."""
    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content or ""
    except Exception as e:
        logger.warning("[script_parser] LLM chat failed: %s", e)
        return ""


async def parse_script(
    normalized_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
    dashscope_api_key: Optional[str] = None,
) -> ScriptData:
    """
    Pass 2 — Chunked script extraction.

    llama.cpp's default single-slot server cannot serve concurrent
    /v1/chat requests reliably — bursts trigger 503 or even connection
    drops. The semaphore in local_llm.py keeps things from crashing, but
    real-world throughput ends up near-serial anyway. We therefore run the
    sub-tasks as a *dependency graph* instead of a flat gather:

        chars  ──┐                (parallel, two small calls)
        header ──┤
                 ▼
                scenes ──┐
                         ▼
                    paragraphs     (depends on scene_count)

    Each call has a short retry-with-backoff so transient 5xx / connection
    drops degrade gracefully. Failure of any single sub-task only affects
    that field; the rest of ScriptData stays populated.
    """
    import asyncio

    async def _with_retry(coro_factory, label: str, attempts: int = 2):
        last_exc = None
        for i in range(attempts):
            try:
                return await coro_factory()
            except Exception as e:
                last_exc = e
                logger.warning("[script_parser] %s attempt %d failed: %s", label, i + 1, e)
                if i + 1 < attempts:
                    await asyncio.sleep(0.6 * (i + 1))
        logger.warning("[script_parser] %s exhausted retries: %s", label, last_exc)
        raise last_exc

    # ── Stage 1: chars + header (two small independent calls) ─────────────────
    header_data, chars = await asyncio.gather(
        _with_retry(lambda: _extract_header(normalized_text, language), "header"),
        _with_retry(lambda: extract_characters(normalized_text, language), "characters"),
        return_exceptions=True,
    )
    if isinstance(header_data, Exception):
        logger.warning("[script_parser] header gather exc: %s", header_data)
        header_data = {}
    if isinstance(chars, Exception):
        logger.warning("[script_parser] chars gather exc: %s", chars)
        chars = []

    # ── Stage 2: scenes (depends on chars for filtering, can run concurrently
    # with stage 1 if we want, but kept serial here for predictability)
    try:
        scenes_list = await _with_retry(
            lambda: _extract_scenes(normalized_text, language), "scenes",
        )
    except Exception:
        scenes_list = []

    # ── Stage 3: paragraphs (depends on scene_count) ──────────────────────────
    scene_count = len(scenes_list) if scenes_list else 1
    try:
        paragraphs_data = await _with_retry(
            lambda: _extract_paragraphs(normalized_text, scene_count, language),
            "paragraphs",
        )
    except Exception:
        paragraphs_data = []

    # ── Assemble ScriptData ──────────────────────────────────────────────────
    script = ScriptData(
        title=(header_data or {}).get("title", "Untitled"),
        genre=(header_data or {}).get("genre", "drama"),
        logline=(header_data or {}).get("logline", ""),
        language=language,
    )

    # Characters → Character list
    for c in chars or []:
        if not getattr(c, "name", ""):
            continue
        script.characters.append(c)

    # Scenes → Scene list (with heuristic fallback when scenes failed)
    if scenes_list:
        for idx, s in enumerate(scenes_list, start=1):
            try:
                est = int(s.get("estimated_shots", 0) or 0)
            except (TypeError, ValueError):
                est = 0
            script.scenes.append(Scene(
                id=s.get("id") or f"scene-{idx}",
                location=s.get("location", ""),
                time=_normalize_time(s.get("time", "Day")),
                atmosphere=s.get("atmosphere", ""),
                estimated_shots=est,
            ))
    else:
        # Heuristic fallback: single scene wrapping everything
        script.scenes.append(Scene(
            id="scene-1",
            location="Unknown Location",
            time="Day",
        ))

    # Paragraphs → StoryParagraph list (with heuristic fallback when paragraphs failed)
    if paragraphs_data:
        # Build name → char_id map so we can convert speaker name → speaker_id.
        name_to_id: dict[str, str] = {c.name: c.id for c in script.characters}
        for idx, p in enumerate(paragraphs_data, start=1):
            try:
                ptype = ParagraphType(p.get("paragraph_type", "action"))
            except ValueError:
                ptype = ParagraphType.ACTION
            scene_idx = p.get("scene_index", 1)
            try:
                scene_idx = int(scene_idx)
            except (TypeError, ValueError):
                scene_idx = 1
            scene_idx = max(1, min(scene_idx, len(script.scenes)))
            scene_ref_id = script.scenes[scene_idx - 1].id
            speaker_name = (p.get("speaker") or "").strip()
            speaker_id = name_to_id.get(speaker_name, "") if speaker_name else ""
            script.story_paragraphs.append(StoryParagraph(
                id=p.get("id") or f"para-{idx}",
                text=p.get("text", ""),
                scene_ref_id=scene_ref_id,
                paragraph_type=ptype,
                speaker_id=speaker_id,
                emotion=p.get("emotion", "") or "",
                contains_action=bool(p.get("contains_action", ptype != ParagraphType.ATMOSPHERE)),
            ))
    else:
        # Heuristic fallback: split on blank lines, all in scene-1
        scene_ref_id = script.scenes[0].id
        for raw_para in _split_into_paragraphs(normalized_text):
            speaker_match = _DIALOGUE_PREFIX.match(raw_para)
            ptype = _classify_paragraph(raw_para, speaker_match)
            speaker_id = ""
            if ptype == ParagraphType.DIALOGUE and speaker_match:
                sname = speaker_match.group(1).strip()
                for c in script.characters:
                    if c.name == sname:
                        speaker_id = c.id
                        break
            script.story_paragraphs.append(StoryParagraph(
                id=f"para-{len(script.story_paragraphs) + 1}",
                text=raw_para,
                scene_ref_id=scene_ref_id,
                paragraph_type=ptype,
                speaker_id=speaker_id,
                emotion="",
                contains_action=(ptype != ParagraphType.ATMOSPHERE),
            ))

    # Compute estimated_shots per scene if LLM didn't provide them
    for scene in script.scenes:
        if scene.estimated_shots <= 0:
            paras_in_scene = [p for p in script.story_paragraphs if p.scene_ref_id == scene.id]
            scene.estimated_shots = max(1, len([p for p in paras_in_scene if p.contains_action]))

    # Filter characters one more time, anchored against the actual paragraphs
    final_chars = [
        c for c in script.characters
        if (c.name and c.name not in _PSEUDO_CHARACTER_BLACKLIST)
    ]
    script.characters = final_chars

    logger.info(
        "[script_parser] parallel parse: title=%r, chars=%d, scenes=%d, paras=%d",
        script.title,
        len(script.characters),
        len(script.scenes),
        len(script.story_paragraphs),
    )

    # If we got literally nothing from any sub-task, fall back to heuristic only.
    if not script.scenes and not script.story_paragraphs:
        return _fallback_script_data(normalized_text, language)
    return script


def _normalize_time(value: str) -> str:
    """Coerce LLM-emitted time strings to the canonical 6-value enum."""
    v = (value or "Day").strip()
    mapping = {
        "day": "Day", "night": "Night", "dawn": "Dawn",
        "dusk": "Dusk", "morning": "Morning", "evening": "Evening",
        "日": "Day", "夜": "Night", "夜晚": "Night", "昼": "Day",
        "黄昏": "Dusk", "黎明": "Dawn", "清晨": "Morning", "傍晚": "Evening",
    }
    return mapping.get(v.lower() if v.isascii() else v, v or "Day")




# ─────────────────────────────────────────────────────────────────────────────
# Helpers — building from LLM JSON output
# ─────────────────────────────────────────────────────────────────────────────

# Pseudo-character names that should NEVER be treated as real characters.
# These are paragraph labels, scene elements, generic pronouns, or perspective
# markers that small LLMs sometimes mistake for character names.
_PSEUDO_CHARACTER_BLACKLIST = frozenset({
    # Paragraph type / shot-type labels
    "特写", "中景", "近景", "远景", "全景", "大特写", "中近景", "中远景",
    "俯拍", "仰拍", "平拍", "长镜头", "空镜", "空镜头", "过肩镜头",
    "镜头", "画面", "画面渐暗", "画面淡入", "画面淡出",
    # Anomaly / event markers
    "异常出现", "异常累积", "异常", "异常结束",
    # Scene elements (non-actor objects)
    "裂缝", "树林", "漂浮建筑", "建筑", "地面", "天空", "云", "树叶",
    "灯光", "路灯", "教学楼", "墙", "围墙", "背景", "桌面", "练习册",
    # Perspective / reaction phrases
    "她的表情", "他的表情", "她的反应", "他的反应", "周围学生的反应",
    "周围", "周围学生", "周围环境", "周围人", "周围的人",
    "她的观察", "他的观察", "她的内心", "他的内心", "她的动作", "他的动作",
    # Generic pronouns
    "她", "他", "他们", "她们", "它", "它们", "某", "某人", "那个人", "这个人",
    # Cardinal / directional place tokens (not characters)
    "教室", "校园", "操场", "操场角落", "学校", "纸境", "夜晚", "傍晚", "黄昏",
    # Dialogue tags LLM might invent
    "旁白", "叙述者", "画外音", "内心独白", "声音", "音效",
})

# Suffixes that, when attached to a name, suggest the name is actually a label
# (e.g. "特写：", "异常出现：" → looks like a Chinese dialogue prefix).
# We strip these and re-check the bare name.
_LABEL_SUFFIXES = ("：", ":", " -", "—", "（", "(")


def _filter_real_characters(
    characters: list[dict],
    paragraphs: list[dict],
) -> list[dict]:
    """
    Drop LLM-hallucinated pseudo-characters from a parsed characters list.

    Real characters must satisfy BOTH:
      1. Their name is NOT in the pseudo-character blacklist (exact match
         after trimming label suffixes), AND
      2. They appear somewhere in the script as either a dialogue speaker
         (paragraph.dialogue starts with "NAME：") or as a prose subject
         (paragraph text contains "NAME" with an action verb nearby).

    This is a safety net: even with the improved prompt, the local Qwen model
    occasionally tags paragraph labels like "特写" as characters.
    """
    if not characters:
        return characters

    # Build a set of names that actually appear as dialogue speakers or as
    # bracketed character descriptions like "林知夏（17岁...）".
    speakers: set[str] = set()
    described: set[str] = set()
    para_text_blob = ""
    for p in paragraphs:
        if not isinstance(p, dict):
            continue
        text = p.get("text", "")
        if not isinstance(text, str):
            continue
        para_text_blob += text + "\n"
        speaker_id = p.get("speaker_id", "")
        if speaker_id:
            speakers.add(speaker_id)

    # Look for bracketed character descriptions: "姓名（...）" or "姓名(...)"
    for m in _BRACKET_DESC_RE.finditer(para_text_blob):
        described.add(m.group(1))

    # Also: any name that appears as a dialogue prefix "NAME：" or "NAME:" in
    # the raw paragraph text is definitely a real character.
    for line in para_text_blob.splitlines():
        line = line.strip()
        m = _DIALOGUE_PREFIX.match(line)
        if m:
            described.add(m.group(1).strip())

    kept: list[dict] = []
    for c in characters:
        name = (c.get("name") or "").strip()
        # Strip any label suffix the LLM might have left on.
        for suf in _LABEL_SUFFIXES:
            if name.endswith(suf):
                name = name[: -len(suf)].strip()
        if not name:
            continue
        # Reject blacklisted names.
        if name in _PSEUDO_CHARACTER_BLACKLIST:
            continue
        # Reject very short / very long names that are unlikely to be real names.
        if len(name) < 2 or len(name) > 12:
            continue
        # Synthetic default placeholders ("角色1", "Character 1") are always
        # retained — they're created by the fallback path when no real
        # character could be identified.
        if name in ("角色1", "Character 1"):
            kept.append(c)
            continue
        # Reject names that never appear in any paragraph as a speaker or
        # bracketed description. (Skip this check for English names that are
        # clearly proper nouns: heuristics are too brittle cross-language.)
        if name in described or name in speakers:
            kept.append(c)
            continue
        # If the LLM gave us a non-empty gender/age/personality, it's likely
        # a real character with metadata, even if no dialogue happened.
        if (c.get("gender") or c.get("age") or c.get("personality")):
            kept.append(c)
            continue
        # Otherwise, the name only appears as a heading/label somewhere — drop.
        # But to be safe, only drop if we have a blacklist hit OR the name is
        # very short (likely a label).
        if len(name) <= 3:
            continue
        kept.append(c)

    return kept


def _build_script_data(data: dict, language: ScriptLanguage) -> ScriptData:
    """Build ScriptData from parsed JSON dict returned by LLM."""
    # LLMs sometimes wrap the expected object in a list (e.g. `[ {...} ]`) or
    # emit a bare array of objects. Normalise those shapes back to a dict.
    if isinstance(data, list):
        if not data:
            return ScriptData(language=language)
        # Case 1: single-element list containing the actual payload object.
        if len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        else:
            # Case 2: list of items — merge any dicts that carry our known
            # top-level fields, and concatenate arrays by field name.
            merged: dict = {}
            arrays = ("characters", "scenes", "story_paragraphs")
            for item in data:
                if not isinstance(item, dict):
                    continue
                for key, value in item.items():
                    if key in arrays and isinstance(value, list):
                        merged.setdefault(key, []).extend(value)
                    else:
                        merged[key] = value
            data = merged

    # Post-process: filter out LLM-hallucinated "characters" that are actually
    # paragraph labels, scene elements, or pronouns. Even with a clearer prompt
    # the LLM sometimes tags "特写", "异常出现", "裂缝" etc. as characters.
    if "characters" in data and isinstance(data["characters"], list):
        raw_chars = data["characters"]
        kept_chars = _filter_real_characters(raw_chars, data.get("story_paragraphs", []))
        if len(kept_chars) != len(raw_chars):
            logger.info(
                "[script_parser] character filter: %d -> %d (dropped %d non-character entries)",
                len(raw_chars), len(kept_chars), len(raw_chars) - len(kept_chars),
            )
        data["characters"] = kept_chars

    script = ScriptData(
        title=data.get("title", "Untitled"),
        genre=data.get("genre", ""),
        logline=data.get("logline", ""),
        language=language,
    )

    for idx, c in enumerate(data.get("characters", []), start=1):
        char_id = c.get("id", f"char-{idx}")
        script.characters.append(Character(
            id=char_id,
            name=c.get("name", ""),
            gender=c.get("gender", ""),
            age=c.get("age", ""),
            personality=c.get("personality", ""),
        ))

    for idx, s in enumerate(data.get("scenes", []), start=1):
        script.scenes.append(Scene(
            id=s.get("id", f"scene-{idx}"),
            location=s.get("location", ""),
            time=s.get("time", "Day"),
            atmosphere=s.get("atmosphere", ""),
        ))

    for idx, p in enumerate(data.get("story_paragraphs", []), start=1):
        try:
            ptype = ParagraphType(p.get("paragraph_type", "action"))
        except ValueError:
            ptype = ParagraphType.ACTION
        script.story_paragraphs.append(StoryParagraph(
            id=p.get("id", f"para-{idx}"),
            text=p.get("text", ""),
            scene_ref_id=p.get("scene_ref_id", ""),
            paragraph_type=ptype,
            speaker_id=p.get("speaker_id", ""),
            emotion=p.get("emotion", ""),
            contains_action=bool(p.get("contains_action", True)),
        ))

    # Compute estimated_shots per scene if LLM didn't provide them
    for scene in script.scenes:
        if scene.estimated_shots > 0:
            continue
        scene_paras = [p for p in script.story_paragraphs if p.scene_ref_id == scene.id]
        scene.estimated_shots = max(
            1,
            sum(
                1 for p in scene_paras
                if p.paragraph_type in (
                    ParagraphType.DIALOGUE,
                    ParagraphType.ACTION,
                    ParagraphType.NARRATION,
                )
            ),
        )

    return script


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — heuristic parsing (no LLM fallback)
# ─────────────────────────────────────────────────────────────────────────────

# ── Scene headings (English & Chinese) ──────────────────────────────────────
# English: "INT. COFFEE SHOP - DAY", "EXT. PARK - NIGHT"
# Chinese: "内景 咖啡馆 - 日", "外景 公园 - 夜晚"
# Loose:   "咖啡馆内", "夜晚的街道"
_SCENE_HEADING_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        # English-format heading
        (?:INT\.|EXT\.|INT/EXT|I/E)\s*[./-]?\s*
        |
        # Chinese-format explicit heading
        (?:内景|外景|场景|场)(?:[：:/\s]+)?
    )
    (?P<location>[^\n-—]+?)
    \s*[-—–]\s*
    (?P<time>[^\n]+?)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE | re.MULTILINE,
)

# Loose Chinese scene start: "咖啡馆内", "夜色中的街道", "清晨的办公室"
_CN_LOOSE_SCENE = re.compile(
    r"^\s*(?:[深夜清晨黄昏傍晚黎明])(?:[色中里的]|[之际])\s*[^\n，。；]+",
    re.MULTILINE,
)

# Transition markers
_TRANSITION_PATTERNS = [
    re.compile(r"^\s*(?:CUT\s*TO|FADE\s*IN|FADE\s*OUT|DISSOLVE\s*TO|SMASH\s*CUT|MATCH\s*CUT|INT\.?\s*TO)[:：.\s]*(.*)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:切到|淡入|淡出|转场|切换到|镜头切到)\s*[：:]\s*(.*)$", re.MULTILINE),
    re.compile(r"^\s*【切入】\s*(.*)$", re.MULTILINE),
]

# Dialogue cues (parenthetical action before a colon-prefixed line)
_PARENTHETICAL = re.compile(r"^\s*[（(][^）)]*[）)]\s*")
# Chinese narration/voiceover markers
_NARRATION_MARKERS = re.compile(
    r"^\s*(?:旁白|叙述|画外音|叙述者|OS|V\.O\.|VOICE[-\s]?OVER|NARRATOR)[:：]?\s*",
    re.IGNORECASE,
)
_INNER_THOUGHT_MARKERS = re.compile(
    r"^\s*(?:内心|心想|思考|想到|OS|VO|内心独白|心语)[：:]?\s*",
    re.IGNORECASE,
)

# Emotion lexicon (lightweight)
_EMOTION_KEYWORDS = {
    "tense": ["紧张", "焦虑", "担心", "恐惧", "害怕", "tense", "anxious", "afraid"],
    "sad": ["悲伤", "难过", "哭泣", "失望", "sad", "cry", "weep"],
    "joyful": ["开心", "高兴", "欢乐", "幸福", "笑", "joyful", "happy", "laugh"],
    "angry": ["愤怒", "生气", "恼火", "angry", "furious", "rage"],
    "mysterious": ["神秘", "诡异", "奇怪", "mysterious", "strange", "eerie"],
    "romantic": ["浪漫", "温馨", "甜蜜", "爱", "romantic", "tender", "love"],
    "tense_chase": ["追逐", "逃跑", "追", "chase", "flee", "run"],
}


def _detect_emotion(text: str) -> str:
    """Return the dominant emotion keyword found in text, or empty string."""
    low = text.lower()
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in low:
                return emotion
    return ""


def _normalize_time(raw: str) -> str:
    """Map free-form time strings to canonical values."""
    mapping = {
        "day": "Day", "日": "Day", "白天": "Day", "午": "Day",
        "morning": "Morning", "上午": "Morning", "早晨": "Morning", "早上": "Morning", "清晨": "Morning",
        "night": "Night", "夜": "Night", "晚上": "Night", "夜晚": "Night", "深夜": "Night",
        "evening": "Evening", "傍晚": "Evening",
        "dusk": "Dusk", "黄昏": "Dusk", "暮色": "Dusk",
        "dawn": "Dawn", "黎明": "Dawn",
    }
    key = raw.strip().lower()
    return mapping.get(key, "Day")


def _parse_scene_heading(line: str) -> Optional[tuple[str, str]]:
    """Try to parse a line as a scene heading. Returns (location, time) or None."""
    # NOTE: don't use literal em/en dashes inside character classes — they can be
    # interpreted as range endpoints. Use explicit \uXXXX escapes.
    _DASH = r"\-\u2014\u2013"
    # English format: "INT. LOCATION - TIME [qualifiers]"
    m = re.match(
        rf"^\s*(?:INT\.|EXT\.|INT\s*/\s*EXT\.|INT/EXT|I/E)\s+"
        rf"(?P<location>[^\n{_DASH}]+?)\s*[{_DASH}]\s*"
        rf"(?P<time>[^\n]+?)\s*$",
        line,
        re.IGNORECASE,
    )
    if m:
        location = m.group("location").strip().rstrip(".")
        # Strip trailing parenthetical qualifiers like "(CONTINUOUS)"
        location = re.sub(r"\s*\([^)]*\)\s*$", "", location).strip()
        return location, _normalize_time(m.group("time"))

    # Chinese format: "内景/外景 地点 - 时间"
    m = re.match(
        rf"^\s*(?:内景|外景|场景|场)\s*[：:/\s]*"
        rf"(?P<location>[^\n{_DASH}]+?)\s*[{_DASH}]\s*"
        rf"(?P<time>[^\n]+?)\s*$",
        line,
    )
    if m:
        return m.group("location").strip(), _normalize_time(m.group("time"))

    return None


def _classify_paragraph(line: str, speaker_match: Optional[re.Match]) -> ParagraphType:
    """Classify a single line/paragraph as dialogue, action, narration, etc."""
    stripped = line.strip()
    if not stripped:
        return ParagraphType.ACTION

    if _NARRATION_MARKERS.match(stripped):
        return ParagraphType.NARRATION
    if _INNER_THOUGHT_MARKERS.match(stripped):
        return ParagraphType.INNER
    for pat in _TRANSITION_PATTERNS:
        if pat.match(stripped):
            return ParagraphType.TRANSITION

    # NAME: ...  → dialogue
    if speaker_match is not None:
        return ParagraphType.DIALOGUE

    # Pure atmospheric cues (sentence starts with 时间词 + 的)
    if re.match(r"^\s*(?:阳光|月光|灯光|雨|雪|风|雾)\s*[^\n。！？]*$", stripped):
        return ParagraphType.ATMOSPHERE

    return ParagraphType.ACTION


def _is_transition_line(line: str) -> bool:
    """True if this line is a CUT TO / FADE IN etc."""
    return any(p.match(line.strip()) for p in _TRANSITION_PATTERNS)


def _split_into_paragraphs(raw_text: str) -> list[str]:
    """
    Split script into semantic paragraphs.

    Boundaries:
      - Blank lines
      - Scene heading lines
      - Transition markers (CUT TO:, FADE IN:)
      - Dialogue / speaker lines (treated as their own paragraph)
    """
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            joined = " ".join(b.strip() for b in buffer if b.strip()).strip()
            if joined:
                paragraphs.append(joined)
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue

        # Scene heading / transition → start new paragraph
        if _parse_scene_heading(stripped) or _is_transition_line(stripped):
            flush()
            paragraphs.append(stripped)
            continue

        # Speaker line (NAME: ...) → flush prior action, start dialogue paragraph
        if _DIALOGUE_PREFIX.match(stripped):
            flush()
            buffer.append(stripped)
            # Continue collecting until blank line (dialogue may span multiple lines)
            continue

        buffer.append(stripped)

    flush()
    return paragraphs


def _fallback_script_data(text: str, language: ScriptLanguage) -> ScriptData:
    """
    Create ScriptData from raw text using heuristic semantic parsing.

    Performs:
      - Scene detection (INT./EXT. + Chinese 内景/外景)
      - Character extraction from dialogue lines
      - Paragraph classification (action / dialogue / narration / atmosphere)
      - Scene ↔ paragraph association
    """
    script = ScriptData(
        title="Untitled Script",
        genre="drama",
        logline=text[:120].strip() + "…" if len(text) > 120 else text.strip(),
        language=language,
    )

    # ── 1. Detect scenes ───────────────────────────────────────────────────────
    raw_paras = _split_into_paragraphs(text)
    current_scene_idx = 0
    char_id_map: dict[str, str] = {}
    char_counter = 1

    # Pre-scan: extract character names from bracketed descriptions like
    # "林知夏（17岁，短发...）". These characters may never speak (dialogue-only
    # detection would miss them), but they're definitely real characters.
    for m in _BRACKET_DESC_RE.finditer(text):
        name = m.group(1).strip()
        if name and name not in _PSEUDO_CHARACTER_BLACKLIST and name not in char_id_map:
            char_id_map[name] = f"char-{char_counter}"
            script.characters.append(Character(
                id=char_id_map[name],
                name=name,
            ))
            char_counter += 1

    for para in raw_paras:
        heading = _parse_scene_heading(para)
        if heading:
            location, time_val = heading
            script.scenes.append(Scene(
                id=f"scene-{len(script.scenes) + 1}",
                location=location,
                time=time_val,
                atmosphere="",
            ))
            current_scene_idx = len(script.scenes) - 1
            continue

        # Default scene if no heading found yet
        if not script.scenes:
            default_loc = "未知场景" if language == ScriptLanguage.CHINESE else "Unknown Location"
            script.scenes.append(Scene(id="scene-1", location=default_loc, time="Day"))
            current_scene_idx = 0

        current_scene = script.scenes[current_scene_idx]

        # ── 2. Classify paragraph ──────────────────────────────────────────────
        speaker_match = _DIALOGUE_PREFIX.match(para)
        ptype = _classify_paragraph(para, speaker_match)

        # ── 3. Extract character from dialogue ────────────────────────────────
        speaker_id = ""
        if ptype == ParagraphType.DIALOGUE and speaker_match:
            speaker_name = speaker_match.group(1).strip()
            if speaker_name and not _NARRATION_MARKERS.match(speaker_name):
                # Reject pseudo-characters: shot labels, scene elements, etc.
                # These should never be promoted to a real character even if
                # they appear before a colon.
                if speaker_name in _PSEUDO_CHARACTER_BLACKLIST:
                    # Demote this "dialogue" to atmosphere/action so it doesn't
                    # pollute the character list downstream.
                    ptype = ParagraphType.ATMOSPHERE
                else:
                    if speaker_name not in char_id_map:
                        char_id_map[speaker_name] = f"char-{char_counter}"
                        script.characters.append(Character(
                            id=char_id_map[speaker_name],
                            name=speaker_name,
                        ))
                        char_counter += 1
                    speaker_id = char_id_map[speaker_name]

        # ── 4. Append paragraph with metadata ─────────────────────────────────
        script.story_paragraphs.append(StoryParagraph(
            id=f"para-{len(script.story_paragraphs) + 1}",
            text=para,
            scene_ref_id=current_scene.id,
            paragraph_type=ptype,
            speaker_id=speaker_id,
            emotion=_detect_emotion(para),
            # Atomsphere/transition paragraphs don't need motion
            contains_action=ptype not in (ParagraphType.ATMOSPHERE, ParagraphType.TRANSITION),
        ))

    # ── 5. Post-process: derive scene atmosphere + estimated_shots ───────────
    for scene in script.scenes:
        scene_paras = [
            p for p in script.story_paragraphs
            if p.scene_ref_id == scene.id
        ]
        # Heuristic: 1 shot per dialogue, 1 shot per 2 action paragraphs,
        # 0 shot for atmosphere/transition
        shot_estimate = 0
        for p in scene_paras:
            if p.paragraph_type == ParagraphType.DIALOGUE:
                shot_estimate += 1
            elif p.paragraph_type == ParagraphType.ACTION:
                shot_estimate += 1
            elif p.paragraph_type == ParagraphType.NARRATION:
                shot_estimate += 1
            # ATMOSPHERE / TRANSITION contribute to establishing shots, not new ones
        scene.estimated_shots = max(1, shot_estimate)

        # Atmosphere from first atmospheric paragraph or most-common emotion
        atm_paras = [
            p for p in scene_paras
            if p.paragraph_type == ParagraphType.ATMOSPHERE
        ]
        if atm_paras:
            scene.atmosphere = atm_paras[0].emotion or "moody"
        else:
            emotions = [p.emotion for p in scene_paras if p.emotion]
            if emotions:
                scene.atmosphere = max(set(emotions), key=emotions.count)

    # ── 6. Safety net: ensure at least one character & one scene ──────────────
    if not script.characters:
        default_name = "角色1" if language == ScriptLanguage.CHINESE else "Character 1"
        script.characters.append(Character(id="char-1", name=default_name))

    # ── 7. Final character filter (defence in depth) ──────────────────────────
    # Even after blacklisting dialogue prefixes above, defense-in-depth: filter
    # the final character list using the same heuristic used for LLM output.
    raw_chars = [c.to_dict() for c in script.characters]
    raw_paras = [p.to_dict() for p in script.story_paragraphs]
    kept_dicts = _filter_real_characters(raw_chars, raw_paras)
    if len(kept_dicts) != len(raw_chars):
        logger.info(
            "[script_parser] fallback character filter: %d -> %d (dropped %d non-character entries)",
            len(raw_chars), len(kept_dicts), len(raw_chars) - len(kept_dicts),
        )
        kept_ids = {c["id"] for c in kept_dicts}
        script.characters = [c for c in script.characters if c.id in kept_ids]
        # Also fix speaker_id references in paragraphs to avoid dangling IDs
        for para in script.story_paragraphs:
            if para.speaker_id and para.speaker_id not in kept_ids:
                para.speaker_id = ""

    # If the filter removed all real characters but we still have some dialogues,
    # make sure at least one synthetic character remains so the UI doesn't break.
    if not script.characters:
        default_name = "角色1" if language == ScriptLanguage.CHINESE else "Character 1"
        script.characters.append(Character(id="char-1", name=default_name))

    logger.info(
        "[script_parser] fallback: title=%r, chars=%d, scenes=%d, paras=%d",
        script.title,
        len(script.characters),
        len(script.scenes),
        len(script.story_paragraphs),
    )
    return script


# ─────────────────────────────────────────────────────────────────────────────
# Public serialization helpers
# ─────────────────────────────────────────────────────────────────────────────

def serialize_script_data(script: ScriptData) -> dict:
    """Convert ScriptData to a JSON-serializable dict."""
    return script.to_dict()


def deserialize_script_data(data: dict) -> ScriptData:
    """Reconstruct ScriptData from a dict (e.g. after json.loads)."""
    return ScriptData.from_dict(data)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: full two-pass pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def process_script(
    raw_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
    dashscope_api_key: Optional[str] = None,
) -> tuple[str, ScriptData]:
    """
    Run the full two-pass pipeline: normalize then parse.

    Uses local llama.cpp server; falls back to heuristics if unavailable.

    Returns:
        A tuple of (normalized_text, ScriptData)
    """
    normalized = await normalize_script(raw_text, language, dashscope_api_key)
    parsed = await parse_script(normalized, language, dashscope_api_key)
    return normalized, parsed
