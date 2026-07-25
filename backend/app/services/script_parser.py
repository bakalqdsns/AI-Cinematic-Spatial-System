"""
Script Parser Service
LLM-powered script normalization and structured parsing.

Two-pass pipeline:
  Pass 1 — normalize:  raw text  → standard screenplay format
  Pass 2 — parse:       normalized text → structured ScriptData dataclasses

Uses local llama.cpp server (Qwen3.5-9B-GGUF) when available, falls back to heuristics.
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "location": self.location,
            "time": self.time,
            "atmosphere": self.atmosphere,
            "estimated_shots": self.estimated_shots,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Scene:
        return cls(
            id=d.get("id", ""),
            location=d.get("location", ""),
            time=d.get("time", "Day"),
            atmosphere=d.get("atmosphere", ""),
            estimated_shots=int(d.get("estimated_shots", 0)),
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
【角色识别规则 — 重要】
═══════════════════════════════════════════════════════════

✅ 应当作为角色（characters 数组中的 name）：
1. 剧本中实际出现的人物姓名（中文人名、英文名皆可）
2. 形式如 "林知夏"、"李明"、"张三" 这种明确人名
3. 形式如 "林知夏（17岁，短发，校服）" 中的 "林知夏"，且 age/gender/personality 字段可从括号内容提取
4. 角色名应当在剧本中多次出现并承担动作或对白

❌ 绝不能作为角色（这些是段落标签/场景元素/视角标记）：
1. 段落类型标记词："特写"、"中景"、"近景"、"远景"、"全景"、"俯拍"、"仰拍"、"长镜头"、"空镜"
2. 异常/事件标记词："异常出现"、"异常累积"、"异常"
3. 场景元素词："裂缝"、"树林"、"漂浮建筑"、"地面"、"天空"、"灯光"、"云"、"树叶"
4. 视角/反应词："她的表情"、"他的反应"、"周围学生的反应"、"周围"、"她的观察"
5. 泛指代词："她"、"他"、"他们"、"它"、"某人"、"那个人"
6. 方位/时间词："教室"、"操场"、"学校"、"夜晚"、"傍晚"、"黄昏"
7. 任何在剧本中只作为段落引导词出现，从不作为动作主语或对白发言者的词

判断标准：当一个词在剧本中：
  - 出现在引号 "..." 前作为说话者 → 是角色
  - 出现在括号 (X岁, ...) 描述中 → 是角色
  - 作为主语驱动动作（"她/他/名字 + 动词"）→ 是角色
  - 仅作为一行段落的开头标签（如"特写：..."、"异常出现：..."）→ ❌ 不是角色

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

_CHARACTER_EXTRACT_SYSTEM_CHINESE = """你是一个专业的角色识别助手。请从剧本文本中识别所有【真正的、有名有姓的人物角色】，输出 JSON 格式。

输出 JSON 必须仅包含一个字段：
- characters: 角色数组，每个包含 id, name, gender, age, personality

═══════════════════════════════════════════════════════════
【角色识别规则 — 重要】
═══════════════════════════════════════════════════════════

✅ 应当作为角色（characters 数组中的 name）：
1. 剧本中实际出现的人物姓名（中文人名、英文名皆可）
2. 形式如 "林知夏"、"李明"、"张三" 这种明确人名
3. 形式如 "林知夏（17岁，短发，校服）" 中的 "林知夏"，且 age/gender/personality 字段可从括号内容提取
4. 角色名应当在剧本中多次出现并承担动作或对白
5. 即便剧本只有一个人物（如独白剧本）也要识别出来

❌ 绝不能作为角色（这些是段落标签/场景元素/视角标记）：
1. 段落类型标记词："特写"、"中景"、"近景"、"远景"、"全景"、"俯拍"、"仰拍"、"长镜头"、"空镜"
2. 异常/事件标记词："异常出现"、"异常累积"、"异常"
3. 场景元素词："裂缝"、"树林"、"漂浮建筑"、"地面"、"天空"、"灯光"、"云"、"树叶"
4. 视角/反应词："她的表情"、"他的反应"、"周围学生的反应"、"周围"、"她的观察"
5. 泛指代词："她"、"他"、"他们"、"它"、"某人"、"那个人"
6. 方位/时间词："教室"、"操场"、"学校"、"夜晚"、"傍晚"、"黄昏"
7. 任何在剧本中只作为段落引导词出现，从不作为动作主语或对白发言者的词

判断标准：当一个词在剧本中：
  - 出现在引号 "..." 前作为说话者 → 是角色
  - 出现在括号 (X岁, ...) 描述中 → 是角色
  - 作为主语驱动动作（"她/他/名字 + 动词"）→ 是角色
  - 仅作为一行段落的开头标签（如"特写：..."、"异常出现：..."）→ ❌ 不是角色

═══════════════════════════════════════════════════════════
字段填写要求
═══════════════════════════════════════════════════════════

- id: 简短字符串如 "char-1", "char-2"，按识别顺序递增
- name: 中文姓名保留中文，英文姓名保留英文
- gender: "male" / "female" / "other" / "" (无法判断留空)
- age: 字符串如 "17"、"30s"、"child"、"adult"；括号内的具体年龄直接取
- personality: 一句话简述角色性格特征，可从剧本动作描述中推断；如无法推断留空

═══════════════════════════════════════════════════════════

只输出 JSON，格式严格如下：
{
  "characters": [
    {"id": "char-1", "name": "林知夏", "gender": "female", "age": "17", "personality": "安静、敏感的学生"}
  ]
}

不要输出 scenes / story_paragraphs / 任何其他字段。不要输出任何解释。"""

_CHARACTER_EXTRACT_SYSTEM_ENGLISH = """You are a professional character identification assistant. Identify all REAL named human characters from the script text and return JSON format.

Output JSON must contain ONLY one field:
- characters: array with id, name, gender, age, personality

CHARACTER IDENTIFICATION RULES — IMPORTANT

YES — these should be in characters[].name:
1. Real human names from the script (Chinese names, English names, all OK)
2. Names like "John Smith", "Mary", "Dr. Watson"
3. Names extracted from bracket descriptions like "John (30s, detective)" — extract age/gender/personality from the brackets
4. Names that recur and drive action or dialogue
5. Even single-character scripts (monologues) — identify the one speaker

NO — these are paragraph labels / scene elements / perspective markers (DO NOT include):
1. Shot-type labels: "Close-up", "Wide shot", "POV", "Tracking shot"
2. Event markers: "Anomaly detected", "Sound effect"
3. Scene elements: "Crack", "Forest", "Sky", "Door", "Tree"
4. Perspective phrases: "Her reaction", "His expression"
5. Generic pronouns: "She", "He", "They", "Someone"
6. Location/time words: "Classroom", "School", "Night"
7. Any word that only appears as a paragraph opening label and never as a speaker or action subject

Field requirements:
- id: short string like "char-1", "char-2", increment in detection order
- name: preserve original language
- gender: "male" / "female" / "other" / "" (empty if unknown)
- age: string like "17", "30s", "child", "adult"; extract from brackets if present
- personality: one-sentence trait description inferred from script; empty if unknown

Output ONLY this JSON shape:
{
  "characters": [
    {"id": "char-1", "name": "...", "gender": "...", "age": "...", "personality": "..."}
  ]
}

Do NOT include scenes / story_paragraphs / any other fields. Do NOT output any explanation."""

_CHARACTER_EXTRACT_SYSTEM_JAPANESE = """あなたはプロフェッショナルなキャラクター識別アシスタントです。脚本から実在する人物キャラクターのみを識別し、JSON形式で返してください。

出力JSONには characters 配列のみを含めてください：
- characters: id, name, gender, age, personality を含む配列

判断基準：中国語版・英語版のルールと同じ。段落ラベル・シーン要素・代名詞は含めないでください。"""


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
            "请从以下剧本文本中识别所有角色：\n\n{text}",
        ),
        ScriptLanguage.ENGLISH: (
            _CHARACTER_EXTRACT_SYSTEM_ENGLISH,
            "Identify all characters from the following script:\n\n{text}",
        ),
        ScriptLanguage.JAPANESE: (
            _CHARACTER_EXTRACT_SYSTEM_JAPANESE,
            "以下の脚本からキャラクターを識別してください：\n\n{text}",
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

    Uses local llama.cpp server (Qwen3.5-9B-GGUF) when available; falls back to
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


async def parse_script(
    normalized_text: str,
    language: ScriptLanguage = ScriptLanguage.CHINESE,
    dashscope_api_key: Optional[str] = None,
) -> ScriptData:
    """
    Pass 2 — Extract structured ScriptData from normalized screenplay text.

    Uses local llama.cpp server (Qwen3.5-9B-GGUF) expecting JSON output; falls
    back to heuristic extraction if the call fails.
    """
    system_prompt, user_template = _build_parse_prompt(language)
    user_text = user_template.format(normalized_script=normalized_text)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(messages, temperature=0.3, max_tokens=4096)
        if content:
            data = _extract_json(content)
            if data is not None:
                result = _build_script_data(data, language)
                logger.info(
                    "[script_parser] parse succeeded: title=%r, chars=%d, scenes=%d, paras=%d",
                    result.title,
                    len(result.characters),
                    len(result.scenes),
                    len(result.story_paragraphs),
                )
                return result
            logger.warning("[script_parser] No JSON object found in LLM output — falling back")
        else:
            logger.warning("[script_parser] Local LLM returned empty — falling back")
    except Exception as e:
        logger.warning("[script_parser] parse exception: %s — falling back", e)

    return _fallback_script_data(normalized_text, language)


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
