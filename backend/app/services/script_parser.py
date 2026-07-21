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
# Language enum
# ─────────────────────────────────────────────────────────────────────────────

class ScriptLanguage(str, Enum):
    CHINESE = "chinese"
    ENGLISH = "english"
    JAPANESE = "japanese"


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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "location": self.location,
            "time": self.time,
            "atmosphere": self.atmosphere,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Scene:
        return cls(
            id=d.get("id", ""),
            location=d.get("location", ""),
            time=d.get("time", "Day"),
            atmosphere=d.get("atmosphere", ""),
        )


@dataclass
class StoryParagraph:
    id: str = ""
    text: str = ""
    scene_ref_id: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "scene_ref_id": self.scene_ref_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StoryParagraph:
        return cls(
            id=d.get("id", ""),
            text=d.get("text", ""),
            scene_ref_id=d.get("scene_ref_id", ""),
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
- scenes: 场景数组，每个包含 id, location, time, atmosphere
- story_paragraphs: 故事段落数组，每个包含 id, text, scene_ref_id

注意事项：
- id 使用简短字符串如 "char-1", "scene-1", "para-1"
- characters 中的 name 必须是剧本中实际出现的角色名
- scenes 中的 location 格式如 "咖啡馆", "街道", "办公室"
- time 只能是: "Day", "Night", "Dawn", "Dusk", "Morning", "Evening"
- atmosphere 是氛围描述如 "紧张", "温馨", "神秘"
- story_paragraphs 的 text 是原始段落文本
- 每个段落必须关联一个场景(scene_ref_id)
- 只输出JSON，不要任何解释"""

_PARSE_SYSTEM_ENGLISH = """You are a professional script analysis assistant. Extract structured information from the script text and return JSON format.

Output JSON must contain:
- title: script title
- genre: genre type
- logline: one-sentence summary
- characters: array with id, name, gender, age, personality
- scenes: array with id, location, time, atmosphere
- story_paragraphs: array with id, text, scene_ref_id

Notes:
- id as short strings like "char-1", "scene-1", "para-1"
- characters name must be actual character names from the script
- scenes location format like "Coffee Shop", "Street", "Office"
- time only: "Day", "Night", "Dawn", "Dusk", "Morning", "Evening"
- atmosphere is mood like "tense", "warm", "mysterious"
- story_paragraphs text is raw paragraph text
- Each paragraph must reference a scene (scene_ref_id)
- Output only JSON, no explanation"""

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


# ─────────────────────────────────────────────────────────────────────────────
# Core async pipeline functions
# ─────────────────────────────────────────────────────────────────────────────

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
            # Strip markdown code fences
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

            data = json.loads(content)
            result = _build_script_data(data, language)
            logger.info(
                "[script_parser] parse succeeded: title=%r, chars=%d, scenes=%d, paras=%d",
                result.title,
                len(result.characters),
                len(result.scenes),
                len(result.story_paragraphs),
            )
            return result
        logger.warning("[script_parser] Local LLM returned empty — falling back")
    except Exception as e:
        logger.warning("[script_parser] parse exception: %s — falling back", e)

    return _fallback_script_data(normalized_text, language)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — building from LLM JSON output
# ─────────────────────────────────────────────────────────────────────────────

def _build_script_data(data: dict, language: ScriptLanguage) -> ScriptData:
    """Build ScriptData from parsed JSON dict returned by LLM."""
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
        script.story_paragraphs.append(StoryParagraph(
            id=p.get("id", f"para-{idx}"),
            text=p.get("text", ""),
            scene_ref_id=p.get("scene_ref_id", ""),
        ))

    return script


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — fallback when LLM is unavailable
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_script_data(text: str, language: ScriptLanguage) -> ScriptData:
    """
    Create minimal ScriptData from raw text when LLM parsing fails.
    Performs simple heuristic extraction of scenes and characters.
    """
    script = ScriptData(
        title="Untitled Script",
        genre="drama",
        logline=text[:120].strip() + "…" if len(text) > 120 else text.strip(),
        language=language,
    )

    # ── extract scenes from INT./EXT. headings ────────────────────────────────
    scene_pattern = re.compile(
        r"(?:INT\.|EXT\.)\s*(.+?)\s*[-–—]\s*(\w+)", re.IGNORECASE
    )
    for idx, m in enumerate(scene_pattern.finditer(text), start=1):
        location = m.group(1).strip()
        time_raw = m.group(2).strip()
        time_val = _normalize_time(time_raw)
        script.scenes.append(Scene(
            id=f"scene-{idx}",
            location=location,
            time=time_val,
            atmosphere="",
        ))

    # Ensure at least one scene
    if not script.scenes:
        loc = "未知场景" if language == ScriptLanguage.CHINESE else "Unknown Location"
        script.scenes.append(Scene(id="scene-1", location=loc, time="Day"))

    # ── extract character names from dialogue lines ─────────────────────────────
    char_pattern = re.compile(r"^([A-Z\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*[:：]", re.MULTILINE)
    seen_names: set[str] = set()
    char_counter = 1
    for m in char_pattern.finditer(text):
        name = m.group(1).strip()
        if name and name not in seen_names and len(seen_names) < 20:
            seen_names.add(name)
            script.characters.append(Character(
                id=f"char-{char_counter}",
                name=name,
            ))
            char_counter += 1

    if not script.characters:
        default_name = "角色1" if language == ScriptLanguage.CHINESE else "Character 1"
        script.characters.append(Character(id="char-1", name=default_name))

    # ── split text into paragraphs ─────────────────────────────────────────────
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    buffer: list[str] = []
    for line in lines:
        buffer.append(line)
        if len("\n".join(buffer)) > 250:
            para_id = f"para-{len(script.story_paragraphs) + 1}"
            script.story_paragraphs.append(StoryParagraph(
                id=para_id,
                text="\n".join(buffer).strip(),
                scene_ref_id=script.scenes[0].id,
            ))
            buffer = []

    if buffer:
        script.story_paragraphs.append(StoryParagraph(
            id=f"para-{len(script.story_paragraphs) + 1}",
            text="\n".join(buffer).strip(),
            scene_ref_id=script.scenes[0].id,
        ))

    logger.info(
        "[script_parser] fallback: title=%r, chars=%d, scenes=%d, paras=%d",
        script.title,
        len(script.characters),
        len(script.scenes),
        len(script.story_paragraphs),
    )
    return script


def _normalize_time(raw: str) -> str:
    """Map free-form time strings to canonical values."""
    mapping = {
        "day": "Day",
        "日": "Day",
        "白天": "Day",
        "上午": "Morning",
        "早晨": "Morning",
        "早上": "Morning",
        "night": "Night",
        "夜": "Night",
        "晚上": "Night",
        "傍晚": "Evening",
        "黄昏": "Dusk",
        "dusk": "Dusk",
        "dawn": "Dawn",
        "黎明": "Dawn",
        "清晨": "Dawn",
    }
    key = raw.strip().lower()
    return mapping.get(key, "Day")


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
