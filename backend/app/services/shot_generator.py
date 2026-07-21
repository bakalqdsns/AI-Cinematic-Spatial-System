"""
Shot Generator Service
LLM-powered shot storyboard generation from parsed ScriptData.

Generates per-scene shot lists with camera movement, shot size, English
visual prompts, keyframe prompts, and character assignments.

Uses local llama.cpp server (Qwen3.5-9B-GGUF) when available; falls back to
heuristic generation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

from .script_parser import (
    Character,
    ScriptData,
    ScriptLanguage,
    Scene,
    StoryParagraph,
)


# ─────────────────────────────────────────────────────────────────────────────
# Camera & shot-size enums
# ─────────────────────────────────────────────────────────────────────────────

class CameraMovement(str, Enum):
    DOLLY_IN = "Dolly In"
    DOLLY_OUT = "Dolly Out"
    PAN_RIGHT = "Pan Right"
    PAN_LEFT = "Pan Left"
    TILT_UP = "Tilt Up"
    TILT_DOWN = "Tilt Down"
    STATIC = "Static"
    HANDHELD = "Handheld"
    TRACKING = "Tracking"
    CRANE_UP = "Crane Up"
    CRANE_DOWN = "Crane Down"
    ZOOM_IN = "Zoom In"
    ZOOM_OUT = "Zoom Out"


class ShotSize(str, Enum):
    EXTREME_CLOSE_UP = "Extreme Close-up"
    CLOSE_UP = "Close-up"
    MEDIUM_CLOSE_UP = "Medium Close-up"
    MEDIUM_SHOT = "Medium Shot"
    MEDIUM_WIDE = "Medium Wide"
    WIDE_SHOT = "Wide Shot"
    EXTREME_WIDE = "Extreme Wide"
    OVER_THE_SHOULDER = "Over-the-Shoulder"
    POV = "POV"
    TWO_SHOT = "Two-Shot"


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VisualPrompts:
    scene_prompt: str = ""       # English scene description prompt
    action_prompt: str = ""      # English character action prompt
    camera_prompt: str = ""      # Camera movement description
    transition_prompt: str = ""  # Transition description (for next shot)

    def to_dict(self) -> dict:
        return {
            "scene_prompt": self.scene_prompt,
            "action_prompt": self.action_prompt,
            "camera_prompt": self.camera_prompt,
            "transition_prompt": self.transition_prompt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VisualPrompts:
        return cls(
            scene_prompt=d.get("scene_prompt", ""),
            action_prompt=d.get("action_prompt", ""),
            camera_prompt=d.get("camera_prompt", ""),
            transition_prompt=d.get("transition_prompt", ""),
        )


@dataclass
class Shot:
    id: str = ""
    scene_id: str = ""
    shot_number: int = 0
    action_summary: str = ""
    dialogue: str = ""
    camera_movement: CameraMovement = CameraMovement.STATIC
    shot_size: ShotSize = ShotSize.MEDIUM_SHOT
    characters: list[str] = field(default_factory=list)  # character IDs
    visual_prompts: VisualPrompts = field(default_factory=VisualPrompts)
    duration_seconds: float = 3.0
    keyframe_start_prompt: str = ""
    keyframe_end_prompt: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scene_id": self.scene_id,
            "shot_number": self.shot_number,
            "action_summary": self.action_summary,
            "dialogue": self.dialogue,
            "camera_movement": self.camera_movement.value,
            "shot_size": self.shot_size.value,
            "characters": self.characters,
            "visual_prompts": self.visual_prompts.to_dict(),
            "duration_seconds": self.duration_seconds,
            "keyframe_start_prompt": self.keyframe_start_prompt,
            "keyframe_end_prompt": self.keyframe_end_prompt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Shot:
        return cls(
            id=d.get("id", ""),
            scene_id=d.get("scene_id", ""),
            shot_number=d.get("shot_number", 0),
            action_summary=d.get("action_summary", ""),
            dialogue=d.get("dialogue", ""),
            camera_movement=_parse_camera(d.get("camera_movement", "Static")),
            shot_size=_parse_shot_size(d.get("shot_size", "Medium Shot")),
            characters=d.get("characters", []),
            visual_prompts=VisualPrompts.from_dict(d.get("visual_prompts", {})),
            duration_seconds=float(d.get("duration_seconds", 3.0)),
            keyframe_start_prompt=d.get("keyframe_start_prompt", ""),
            keyframe_end_prompt=d.get("keyframe_end_prompt", ""),
        )


@dataclass
class SceneTransition:
    from_scene_id: str = ""
    to_scene_id: str = ""
    transition_type: str = "cut"  # "cut", "dissolve", "fade", "wipe"
    transition_prompt: str = ""

    def to_dict(self) -> dict:
        return {
            "from_scene_id": self.from_scene_id,
            "to_scene_id": self.to_scene_id,
            "transition_type": self.transition_type,
            "transition_prompt": self.transition_prompt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SceneTransition:
        return cls(
            from_scene_id=d.get("from_scene_id", ""),
            to_scene_id=d.get("to_scene_id", ""),
            transition_type=d.get("transition_type", "cut"),
            transition_prompt=d.get("transition_prompt", ""),
        )


@dataclass
class CharacterActionSequence:
    character_id: str = ""
    character_name: str = ""
    shots: list[str] = field(default_factory=list)  # shot IDs
    action_sequence_prompt: str = ""  # Combined English prompt
    intensity_curve: list[float] = field(default_factory=list)  # 0-1 energy per shot

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "character_name": self.character_name,
            "shots": self.shots,
            "action_sequence_prompt": self.action_sequence_prompt,
            "intensity_curve": self.intensity_curve,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CharacterActionSequence:
        return cls(
            character_id=d.get("character_id", ""),
            character_name=d.get("character_name", ""),
            shots=d.get("shots", []),
            action_sequence_prompt=d.get("action_sequence_prompt", ""),
            intensity_curve=list(d.get("intensity_curve", [])),
        )


# ─────────────────────────────────────────────────────────────────────────────
# System prompts — shot generation
# ─────────────────────────────────────────────────────────────────────────────

_SHOT_GENERATION_SYSTEM_CHINESE = """你是一个专业的分镜师。请根据以下剧本信息，生成详细的分镜表。

要求：
1. 每个场景生成6-8个分镜
2. 分镜必须包含：镜头号（顺序编号）、景别（使用指定枚举）、运镜（使用指定枚举）、动作描述、人物列表、预估时长
3. 为每个分镜生成英文视觉提示词（scene_prompt描述场景，action_prompt描述人物动作）
4. 确保分镜之间的动作和情节连贯
5. 运镜要符合情节需要（如紧张场景可用手持或快速推拉）

景别枚举值：Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Wide, Wide Shot, Extreme Wide, Over-the-Shoulder, POV, Two-Shot

运镜枚举值：Dolly In, Dolly Out, Pan Right, Pan Left, Tilt Up, Tilt Down, Static, Handheld, Tracking, Crane Up, Crane Down, Zoom In, Zoom Out

输出格式（严格JSON数组）：
[
  {
    "id": "shot-1",
    "scene_id": "scene-1",
    "shot_number": 1,
    "action_summary": "动作描述",
    "dialogue": "对白（无则为空）",
    "camera_movement": "Static",
    "shot_size": "Wide Shot",
    "characters": ["char-1"],
    "scene_prompt": "English: A wide shot of a coffee shop interior, warm sunlight streaming through windows...",
    "action_prompt": "English: A woman sits alone at a table, nervously stirring her coffee...",
    "camera_prompt": "Slow dolly in to build tension",
    "duration_seconds": 4.0,
    "keyframe_start_prompt": "English: Woman sits, cup in hand, looking toward door...",
    "keyframe_end_prompt": "English: Close-up on worried expression as phone buzzes..."
  }
]

只输出JSON数组，不要任何解释。"""

_SHOT_GENERATION_SYSTEM_ENGLISH = """You are a professional storyboard artist. Generate a detailed shot list based on the following script information.

Requirements:
1. Generate 6-8 shots per scene
2. Each shot must include: shot number (sequential), shot size (use enum), camera movement (use enum), action description, character list, estimated duration
3. Generate English visual prompts for each shot (scene_prompt for scene, action_prompt for character action)
4. Ensure continuity of action and plot between shots
5. Camera movements should match the plot needs

Shot size enum values: Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Wide, Wide Shot, Extreme Wide, Over-the-Shoulder, POV, Two-Shot

Camera movement enum values: Dolly In, Dolly Out, Pan Right, Pan Left, Tilt Up, Tilt Down, Static, Handheld, Tracking, Crane Up, Crane Down, Zoom In, Zoom Out

Output: strict JSON array only, no explanation."""

_SHOT_GENERATION_SYSTEM_JAPANESE = """あなたはプロフェッショナルなストーリーボードアーティストです。以下の脚本情報に基づいて詳細なショットリストを生成してください。

要件：
1. シーンごとに6-8ショット生成
2. 各ショットには shot_number, camera_movement, shot_size, action_summary, characters, duration を含む
3. 各ショットに英語の visual prompts を生成
4. ショット間の継続性を確保

出力：JSON配列のみ"""


# ─────────────────────────────────────────────────────────────────────────────
# Core async generation function
# ─────────────────────────────────────────────────────────────────────────────

def _build_shot_prompt(script_data: ScriptData, language: ScriptLanguage) -> str:
    """Build the user-facing prompt for shot generation from ScriptData."""
    scenes_text = "\n".join(
        f"  - {s.id}: {s.location} - {s.time} ({s.atmosphere})"
        for s in script_data.scenes
    )
    chars_text = "\n".join(
        f"  - {c.id}: {c.name} (gender:{c.gender}, age:{c.age}, personality:{c.personality})"
        for c in script_data.characters
    )
    paras_text = "\n".join(
        f"  [{p.scene_ref_id}] {p.text[:120]}..."
        for p in script_data.story_paragraphs
    )

    return f"""剧本标题: {script_data.title}
题材: {script_data.genre}
简介: {script_data.logline}

场景列表:
{scenes_text}

角色列表:
{chars_text}

故事段落:
{paras_text}

请生成完整分镜表："""


async def generate_shots(
    script_data: ScriptData,
    shots_per_scene: int = 6,
    language: Optional[ScriptLanguage] = None,
) -> list[Shot]:
    """
    Generate shot storyboard from ScriptData using LLM.

    Args:
        script_data: Structured script data from parse_script()
        shots_per_scene: Minimum shots per scene (LLM may generate more)
        language: Override the script's detected language (None = use script's)

    Returns:
        List of Shot dataclasses ordered by shot_number
    """
    lang = language or script_data.language
    prompts = {
        ScriptLanguage.CHINESE: _SHOT_GENERATION_SYSTEM_CHINESE,
        ScriptLanguage.ENGLISH: _SHOT_GENERATION_SYSTEM_ENGLISH,
        ScriptLanguage.JAPANESE: _SHOT_GENERATION_SYSTEM_JAPANESE,
    }
    system_prompt = prompts[lang]
    user_prompt = _build_shot_prompt(script_data, lang)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        from .local_llm import get_llm_client
        client = get_llm_client()
        content = await client.chat(messages, temperature=0.4, max_tokens=8192)
        if content:
            # Strip markdown code fences
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

            data = json.loads(content)
            shots = _build_shots_from_json(data)
            logger.info(
                "[shot_generator] generated %d shots for %d scenes",
                len(shots),
                len(script_data.scenes),
            )
            return shots
        logger.warning("[shot_generator] Local LLM returned empty — falling back")
    except Exception as e:
        logger.warning("[shot_generator] shot gen exception: %s — falling back", e)

    return _fallback_shots(script_data)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — building from LLM JSON output
# ─────────────────────────────────────────────────────────────────────────────

def _build_shots_from_json(data: list | dict) -> list[Shot]:
    """
    Build a list of Shot objects from raw JSON returned by LLM.
    Handles both list-of-dicts and wrapped {"shots": [...]} formats.
    """
    if isinstance(data, dict):
        data = data.get("shots", [data])

    shots: list[Shot] = []
    for idx, item in enumerate(data, start=1):
        try:
            shot = Shot(
                id=item.get("id", f"shot-{idx}"),
                scene_id=item.get("scene_id", ""),
                shot_number=item.get("shot_number", idx),
                action_summary=item.get("action_summary", ""),
                dialogue=item.get("dialogue", ""),
                camera_movement=_parse_camera(item.get("camera_movement", "Static")),
                shot_size=_parse_shot_size(item.get("shot_size", "Medium Shot")),
                characters=item.get("characters", []),
                visual_prompts=VisualPrompts(
                    scene_prompt=item.get("scene_prompt", ""),
                    action_prompt=item.get("action_prompt", ""),
                    camera_prompt=item.get("camera_prompt", ""),
                    transition_prompt=item.get("transition_prompt", ""),
                ),
                duration_seconds=float(item.get("duration_seconds", 3.0)),
                keyframe_start_prompt=item.get("keyframe_start_prompt", ""),
                keyframe_end_prompt=item.get("keyframe_end_prompt", ""),
            )
            shots.append(shot)
        except Exception as e:
            logger.warning("[shot_generator] Failed to parse shot item %d: %s", idx, e)
            continue

    return shots


def _parse_camera(value: str) -> CameraMovement:
    """Map a string value to CameraMovement enum (case-insensitive, fuzzy)."""
    normalized = value.lower().replace(" ", "").replace("-", "")
    for cm in CameraMovement:
        if cm.value.lower().replace(" ", "").replace("-", "") == normalized:
            return cm
    # Partial match fallback
    for cm in CameraMovement:
        if normalized in cm.value.lower().replace(" ", ""):
            return cm
    return CameraMovement.STATIC


def _parse_shot_size(value: str) -> ShotSize:
    """Map a string value to ShotSize enum (case-insensitive, fuzzy)."""
    normalized = value.lower().replace(" ", "").replace("-", "")
    for ss in ShotSize:
        if ss.value.lower().replace(" ", "").replace("-", "") == normalized:
            return ss
    for ss in ShotSize:
        if normalized in ss.value.lower().replace(" ", ""):
            return ss
    return ShotSize.MEDIUM_SHOT


# ─────────────────────────────────────────────────────────────────────────────
# Fallback — heuristic generation when LLM is unavailable
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_shots(script_data: ScriptData) -> list[Shot]:
    """
    Generate a basic shot list from ScriptData without LLM.

    Strategy: one shot per 2 story paragraphs, cycling through shot sizes.
    """
    shots: list[Shot] = []
    shot_num = 1

    for scene in script_data.scenes:
        scene_paras = [
            p for p in script_data.story_paragraphs
            if p.scene_ref_id == scene.id
        ]

        # Group paragraphs into shot chunks
        for i in range(0, len(scene_paras), 2):
            chunk = scene_paras[i : i + 2]
            text = " ".join(p.text for p in chunk)[:200]
            scene_char_ids = [c.id for c in script_data.characters]

            shot_sizes_cycle = [
                ShotSize.WIDE_SHOT,
                ShotSize.MEDIUM_SHOT,
                ShotSize.CLOSE_UP,
                ShotSize.MEDIUM_CLOSE_UP,
            ]
            shot_size = shot_sizes_cycle[(shot_num - 1) % len(shot_sizes_cycle)]

            scene_prompt = (
                f"A cinematic shot of {scene.location}, {scene.time.lower()}. "
                f"{scene.atmosphere} atmosphere."
            )

            shots.append(Shot(
                id=f"shot-{shot_num}",
                scene_id=scene.id,
                shot_number=shot_num,
                action_summary=text,
                camera_movement=CameraMovement.STATIC,
                shot_size=shot_size,
                characters=scene_char_ids,
                visual_prompts=VisualPrompts(
                    scene_prompt=scene_prompt,
                    action_prompt=text,
                    camera_prompt="Static camera, establishing the scene.",
                ),
                duration_seconds=3.0,
                keyframe_start_prompt=scene_prompt,
                keyframe_end_prompt=f"Continuation of {scene.location} scene.",
            ))
            shot_num += 1

    logger.info("[shot_generator] fallback generated %d shots", len(shots))
    return shots


# ─────────────────────────────────────────────────────────────────────────────
# Post-generation helpers
# ─────────────────────────────────────────────────────────────────────────────

def generate_scene_transitions(shots: list[Shot]) -> list[SceneTransition]:
    """
    Generate transition descriptors between consecutive shots that belong to
    different scenes.
    """
    transitions: list[SceneTransition] = []
    for i in range(len(shots) - 1):
        curr = shots[i]
        nxt = shots[i + 1]

        if curr.scene_id == nxt.scene_id:
            continue

        # Build a descriptive prompt
        prompt_parts = [curr.visual_prompts.scene_prompt]
        if curr.visual_prompts.transition_prompt:
            prompt_parts.append(curr.visual_prompts.transition_prompt)
        prompt_parts.append(nxt.visual_prompts.scene_prompt)
        transition_prompt = " — ".join(p for p in prompt_parts if p)

        transitions.append(SceneTransition(
            from_scene_id=curr.scene_id,
            to_scene_id=nxt.scene_id,
            transition_type="dissolve",
            transition_prompt=transition_prompt,
        ))

    return transitions


def generate_character_action_sequences(
    shots: list[Shot],
    characters: list[Character],
) -> list[CharacterActionSequence]:
    """
    Build per-character action sequences across the shot list.

    Each sequence includes:
      - shots: list of shot IDs the character appears in
      - action_sequence_prompt: concatenated English action prompts
      - intensity_curve: oscillating 0-1 energy values per shot
    """
    sequences: list[CharacterActionSequence] = []

    for char in characters:
        char_shots = [s for s in shots if char.id in s.characters]
        if not char_shots:
            continue

        actions = [
            s.visual_prompts.action_prompt or s.action_summary
            for s in char_shots[:5]
        ]
        combined = " then ".join(actions)

        # Simple oscillating intensity curve
        intensity = [
            round(0.3 + 0.7 * abs((j % 6) / 5 - 0.5), 3)
            for j in range(len(char_shots))
        ]

        sequences.append(CharacterActionSequence(
            character_id=char.id,
            character_name=char.name,
            shots=[s.id for s in char_shots],
            action_sequence_prompt=combined,
            intensity_curve=intensity,
        ))

    return sequences


# ─────────────────────────────────────────────────────────────────────────────
# Serialization helpers
# ─────────────────────────────────────────────────────────────────────────────

def serialize_shots(shots: list[Shot]) -> list[dict]:
    """Serialize a list of Shot objects to JSON-serializable dicts."""
    return [s.to_dict() for s in shots]


def deserialize_shots(data: list[dict]) -> list[Shot]:
    """Reconstruct a list of Shot objects from dicts."""
    return _build_shots_from_json(data)


def serialize_transitions(transitions: list[SceneTransition]) -> list[dict]:
    return [t.to_dict() for t in transitions]


def deserialize_transitions(data: list[dict]) -> list[SceneTransition]:
    return [SceneTransition.from_dict(t) for t in data]


def serialize_action_sequences(
    sequences: list[CharacterActionSequence],
) -> list[dict]:
    return [s.to_dict() for s in sequences]


def deserialize_action_sequences(
    data: list[dict],
) -> list[CharacterActionSequence]:
    return [CharacterActionSequence.from_dict(s) for s in data]
