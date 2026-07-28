"""
Shot Generator Service
LLM-powered shot storyboard generation from parsed ScriptData.

Generates per-scene shot lists with camera movement, shot size, English
visual prompts, keyframe prompts, and character assignments.

Uses local llama.cpp server (Qwen2.5-7B-Instruct Q4_K_M GGUF) when available; falls back to
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
    ParagraphType,
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
1. **每个故事段落（story_paragraph）必须至少对应一个分镜**；段落是分镜的核心驱动单元，不要漏掉任何段落
2. 全剧共生成的总分镜数应**不少于故事段落数**；可在重要段落上拆出 2-3 个分镜（同一动作的不同景别/运镜）以保证密度，但绝不裁减段落
3. **shot_number 必须全局连续递增**（1, 2, 3, ...），跨场景也要连续，绝对不能同一 shot_number 重复或乱序
4. 分镜必须包含：镜头号（全局顺序编号）、景别（使用指定枚举）、运镜（使用指定枚举）、动作描述、人物列表、预估时长
5. 为每个分镜生成英文视觉提示词（scene_prompt描述场景，action_prompt描述人物动作）
6. 确保分镜之间的动作和情节连贯
7. 运镜要符合情节需要（如紧张场景可用手持或快速推拉）

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
1. **Every story paragraph must produce at least one shot.** Paragraphs are the primary unit — never drop one.
2. Total shot count should be **at least the number of story paragraphs**; important paragraphs may split into 2-3 shots (different shot sizes / camera movements) for density.
3. **shot_number must be globally sequential (1, 2, 3, …)** across scenes. No duplicates, no gaps, no resets per scene.
4. Each shot must include: shot number (global sequential), shot size (use enum), camera movement (use enum), action description, character list, estimated duration
5. Generate English visual prompts for each shot (scene_prompt for scene, action_prompt for character action)
6. Ensure continuity of action and plot between shots
7. Camera movements should match the plot needs

Shot size enum values: Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Wide, Wide Shot, Extreme Wide, Over-the-Shoulder, POV, Two-Shot

Camera movement enum values: Dolly In, Dolly Out, Pan Right, Pan Left, Tilt Up, Tilt Down, Static, Handheld, Tracking, Crane Up, Crane Down, Zoom In, Zoom Out

Output: strict JSON array only, no explanation."""

_SHOT_GENERATION_SYSTEM_JAPANESE = """あなたはプロフェッショナルなストーリーボードアーティストです。以下の脚本情報に基づいて詳細なショットリストを生成してください。

要件：
1. **各ストーリーパラグラフ（段落）は必ず1つ以上のショットを生成すること**。段落を絶対に省略しない。
2. 総ショット数は **段落数以上** とすること。重要な段落は2-3ショットに分割してもよい。
3. **shot_number はシーンを跨いでグローバルに連番 (1, 2, 3, …)** とすること。重複・欠番・シーン単位リセット禁止。
4. 各ショットには shot_number, camera_movement, shot_size, action_summary, characters, duration を含む
5. 各ショットに英語の visual prompts を生成
6. ショット間の継続性を確保
7. カメラムーブはプロットに合わせること

出力:JSON配列のみ"""


# ─────────────────────────────────────────────────────────────────────────────
# Core async generation function
# ─────────────────────────────────────────────────────────────────────────────

def _build_shot_prompt(script_data: ScriptData, language: ScriptLanguage, shots_per_scene: int) -> str:
    """Build the user-facing prompt for shot generation from ScriptData."""
    scenes_text = "\n".join(
        f"  - {s.id}: {s.location} - {s.time} ({s.atmosphere})"
        for s in script_data.scenes
    )
    chars_text = "\n".join(
        f"  - {c.id}: {c.name} (gender:{c.gender}, age:{c.age}, personality:{c.personality})"
        for c in script_data.characters
    )
    # Numbered paragraph index for unambiguous LLM-side references
    paras_lines = []
    for i, p in enumerate(script_data.story_paragraphs, start=1):
        paras_lines.append(
            f"  P{i:02d} [{p.scene_ref_id}] type={p.paragraph_type.value} speaker={p.speaker_id}: {p.text[:140]}"
        )
    paras_text = "\n".join(paras_lines)

    n_scenes = len(script_data.scenes)
    n_paras = len(script_data.story_paragraphs)
    min_total = max(shots_per_scene * n_scenes, n_paras)
    para_index_label = f"P01..P{n_paras:02d}"

    return f"""剧本标题: {script_data.title}
题材: {script_data.genre}
简介: {script_data.logline}

统计:
  - 场景数: {n_scenes}
  - 故事段落数: {n_paras}
  - 分镜总数下限: {min_total} (每场景至少 {shots_per_scene} 个, 且每个段落至少 1 个, 取较大值)

场景列表:
{scenes_text}

角色列表:
{chars_text}

故事段落 (每个段落必须至少对应一个分镜 {para_index_label}):
{paras_text}

请生成完整分镜表,确保 shot_number 全局 1..{min_total} 连续递增:"""


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
    user_prompt = _build_shot_prompt(script_data, lang, shots_per_scene)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        from .local_llm import get_llm_client
        from .script_parser import _extract_json
        client = get_llm_client()
        content = await client.chat(messages, temperature=0.4, max_tokens=8192)
        if content:
            data = _extract_json(content)
            if data is not None:
                shots = _build_shots_from_json(data)
                _validate_shot_characters(shots, script_data)
                _renumber_shots(shots)
                logger.info(
                    "[shot_generator] generated %d shots for %d scenes (%d paragraphs)",
                    len(shots),
                    len(script_data.scenes),
                    len(script_data.story_paragraphs),
                )
                return shots
            logger.warning("[shot_generator] No JSON found in LLM output — falling back")
        else:
            logger.warning("[shot_generator] Local LLM returned empty — falling back")
    except Exception as e:
        logger.warning("[shot_generator] shot gen exception: %s — falling back", e)

    shots = _fallback_shots(script_data)
    _renumber_shots(shots)
    return shots


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


def _validate_shot_characters(shots: list[Shot], script_data: ScriptData) -> None:
    """
    Character-first validation: ensure every shot's `characters` field
    contains only character IDs that exist in script_data.characters, and
    that the shot is associated with at least one present character for its
    scene (a speaker in that scene, or the LLM-emitted list if non-empty).

    Mutates `shots` in place. Drops unknown IDs, fills in scene speakers
    when the LLM left the field empty.
    """
    valid_char_ids = {c.id for c in script_data.characters if c.id}

    # Pre-compute per-scene speaker sets (the canonical "characters present in this scene").
    scene_speakers: dict[str, set[str]] = {}
    for para in script_data.story_paragraphs:
        scene_speakers.setdefault(para.scene_ref_id, set()).add(para.speaker_id)

    for shot in shots:
        # 1. Drop unknown IDs (LLM hallucinated)
        filtered = [cid for cid in shot.characters if cid in valid_char_ids]

        # 2. If empty, fall back to scene's speakers — the characters who
        #    must be on-screen if anyone is speaking in that scene.
        scene_id = shot.scene_id or next(
            (p.scene_ref_id for p in script_data.story_paragraphs if shot.scene_id == p.scene_ref_id),
            "",
        )
        scene_present = scene_speakers.get(scene_id, set())
        scene_present = {cid for cid in scene_present if cid in valid_char_ids}

        if not filtered and scene_present:
            # If the shot is in a scene where characters actually speak, link them
            filtered = sorted(scene_present)

        shot.characters = filtered


def _renumber_shots(shots: list[Shot]) -> None:
    """
    Guarantee globally-sequential, gap-free shot numbers in display order.

    The LLM sometimes emits shot_number values that are non-sequential
    (e.g. resets per scene, gaps after merging, duplicate values, or even
    string keys). The frontend then sorts lexicographically and produces
    "01, 02, 03, 04, 05, 10, 06, 07, 08, 09". We normalize by:

      1. Sorting by (scene_id, shot_number) with shot_number coerced to int.
      2. Renumbering 1..N in that order, mutating both `shot_number` and the
         trailing integer in `id` (e.g. "shot-3" -> "shot-3" stays, but if id
         was "shot-10" and it becomes shot 3 we rewrite it).

    Also: synthesize fallback IDs if the LLM emitted empty/duplicate ids,
    since downstream UI relies on id stability.
    """
    if not shots:
        return

    def _sort_key(s: Shot) -> tuple[int, int]:
        try:
            sn = int(s.shot_number)
        except (TypeError, ValueError):
            sn = 0
        # Use scene_id ordinal by appearance (stable) when shot_number ties
        return (0, sn)

    shots.sort(key=_sort_key)

    seen_ids: set[str] = set()
    for idx, shot in enumerate(shots, start=1):
        # Derive a stable id; preserve LLM-emitted id if unique, else rename
        if not shot.id or shot.id in seen_ids:
            shot.id = f"shot-{idx}"
        seen_ids.add(shot.id)
        shot.shot_number = idx


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
    Generate a contextual shot list from ScriptData without LLM.

    Shot-suggestion rules per paragraph type:
      - atmosphere → opening Wide / Extreme Wide establishing shot
      - action     → Medium Shot (default) or POV if first-person
      - dialogue   → Close-up / Two-Shot (with speaker)
      - narration  → Close-up or Medium Close-up
      - inner      → Extreme Close-up (face/eyes)
      - transition → dissolve cut (no new shot)

    Each shot's duration is driven by emotion intensity:
      - tense / angry / chase → 2.0s (fast cut)
      - sad / mysterious     → 4.5s (slow)
      - joyful / romantic    → 3.5s
      - default              → 3.0s
    """
    shots: list[Shot] = []
    shot_num = 1

    # Lookup character id → name
    char_name_map = {c.id: c.name for c in script_data.characters}

    for scene in script_data.scenes:
        scene_paras = [
            p for p in script_data.story_paragraphs
            if p.scene_ref_id == scene.id
        ]

        opened_with_estab = False

        for para in scene_paras:
            if para.paragraph_type == ParagraphType.TRANSITION:
                # Transitions don't create shots themselves
                continue

            # Decide shot size based on paragraph type
            if para.paragraph_type == ParagraphType.ATMOSPHERE:
                shot_size = ShotSize.EXTREME_WIDE if not opened_with_estab else ShotSize.WIDE_SHOT
                opened_with_estab = True
                camera_movement = CameraMovement.PAN_RIGHT
                duration = 3.5
            elif para.paragraph_type == ParagraphType.DIALOGUE:
                # Two-Shot if there are 2+ characters in scene, else Close-up
                chars_in_scene = [
                    c.id for c in script_data.characters
                    if c.id in {p.speaker_id for p in scene_paras if p.speaker_id}
                ]
                shot_size = ShotSize.TWO_SHOT if len(chars_in_scene) >= 2 else ShotSize.CLOSE_UP
                camera_movement = CameraMovement.STATIC
                duration = 2.5
            elif para.paragraph_type == ParagraphType.INNER:
                shot_size = ShotSize.EXTREME_CLOSE_UP
                camera_movement = CameraMovement.DOLLY_IN
                duration = 3.5
            elif para.paragraph_type == ParagraphType.NARRATION:
                shot_size = ShotSize.MEDIUM_CLOSE_UP
                camera_movement = CameraMovement.STATIC
                duration = 3.0
            else:  # ACTION
                # First action in scene: establish with wider shot
                shot_size = ShotSize.MEDIUM_WIDE if not opened_with_estab else ShotSize.MEDIUM_SHOT
                opened_with_estab = True
                # Detect chase / high-intensity motion
                if para.emotion in ("tense_chase",):
                    camera_movement = CameraMovement.HANDHELD
                    duration = 2.0
                else:
                    camera_movement = CameraMovement.TRACKING
                    duration = 3.0

            # Infer emotion from paragraph type and content when LLM didn't set it
            inferred_emotion = para.emotion or ""
            if not inferred_emotion:
                if para.paragraph_type == ParagraphType.DIALOGUE:
                    if "！" in para.text or "!" in para.text or any(
                        kw in para.text for kw in ["猛地", "突然", "惊叫", "喊道", "大喊"]
                    ):
                        inferred_emotion = "tense"
                    elif any(
                        kw in para.text for kw in ["低声", "叹息", "沉默", "轻声", "低声说"]
                    ):
                        inferred_emotion = "sad"
                    else:
                        inferred_emotion = "calm"
                elif para.paragraph_type == ParagraphType.NARRATION:
                    if para.text.startswith("...") or para.text.startswith("……"):
                        inferred_emotion = "mysterious"
                    elif any(
                        kw in para.text for kw in ["回忆", "记得", "曾经", "过去"]
                    ):
                        inferred_emotion = "sad"
                    else:
                        inferred_emotion = "calm"
                elif para.paragraph_type == ParagraphType.INNER:
                    inferred_emotion = "dramatic"
                elif para.paragraph_type == ParagraphType.ATMOSPHERE:
                    inferred_emotion = "calm"
                else:
                    inferred_emotion = "calm"

            # Emotion-based duration override
            if inferred_emotion in ("tense", "angry"):
                duration = min(duration, 2.5)
            elif inferred_emotion in ("sad", "mysterious"):
                duration = max(duration, 4.0)
            elif inferred_emotion in ("romantic",):
                duration = max(duration, 3.5)

            scene_prompt = (
                f"A cinematic shot of {scene.location}, {scene.time.lower()}. "
                f"{scene.atmosphere} atmosphere. "
                f"{para.text[:80]}"
            )
            action_prompt = para.text

            # Collect characters in this paragraph. Character-first rules:
            #   - DIALOGUE/INNER: speaker_id is the primary character
            #   - ACTION: any character whose id is referenced in the para text
            #     OR any character with a dialogue in this scene (always present)
            #   - ATMOSPHERE/NARRATION: characters with a dialogue in the scene
            #     (they must be somewhere on screen if anyone is talking)
            chars_in_para: list[str] = []
            seen: set[str] = set()
            for ch_id in (para.speaker_id, ):
                if ch_id and ch_id in {c.id for c in script_data.characters}:
                    if ch_id not in seen:
                        chars_in_para.append(ch_id)
                        seen.add(ch_id)

            scene_speaker_ids = {
                p.speaker_id for p in scene_paras if p.speaker_id
            }
            for ch_id in scene_speaker_ids:
                if ch_id in {c.id for c in script_data.characters} and ch_id not in seen:
                    chars_in_para.append(ch_id)
                    seen.add(ch_id)

            shots.append(Shot(
                id=f"shot-{shot_num}",
                scene_id=scene.id,
                shot_number=shot_num,
                action_summary=para.text,
                dialogue=para.text if para.paragraph_type == ParagraphType.DIALOGUE else "",
                camera_movement=camera_movement,
                shot_size=shot_size,
                characters=chars_in_para,
                visual_prompts=VisualPrompts(
                    scene_prompt=scene_prompt,
                    action_prompt=action_prompt,
                    camera_prompt=f"{camera_movement.value} {shot_size.value} framing.",
                ),
                duration_seconds=duration,
                keyframe_start_prompt=scene_prompt,
                keyframe_end_prompt=f"Continuation: {para.text[:80]}",
            ))
            shot_num += 1

    logger.info("[shot_generator] fallback generated %d shots", len(shots))
    _validate_shot_characters(shots, script_data)
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


def _smooth_curve(values: list[float], window: int = 3) -> list[float]:
    """Apply a sliding average to smooth the intensity curve."""
    if len(values) <= 1:
        return values
    result = []
    for i in range(len(values)):
        start = max(0, i - window // 2)
        end = min(len(values), i + window // 2 + 1)
        result.append(round(sum(values[start:end]) / (end - start), 3))
    return result


def generate_character_action_sequences(
    shots: list[Shot],
    characters: list[Character],
    paragraphs: list[StoryParagraph] | None = None,
) -> list[CharacterActionSequence]:
    """
    Build per-character action sequences across the shot list.

    Each sequence includes:
      - shots: list of shot IDs the character appears in
      - action_sequence_prompt: concatenated English action prompts
      - intensity_curve: 0-1 energy values derived from paragraph emotions,
        smoothed with a 3-point sliding average

    When paragraphs are not provided (backwards-compatible), falls back to the
    original oscillating pattern.
    """
    EMOTION_INTENSITY: dict[str, float] = {
        "tense": 1.0,
        "suspenseful": 0.9,
        "dramatic": 0.85,
        "exciting": 0.8,
        "mysterious": 0.6,
        "romantic": 0.4,
        "joyful": 0.5,
        "sad": 0.3,
        "calm": 0.2,
        "peaceful": 0.15,
    }

    sequences: list[CharacterActionSequence] = []
    para_map: dict[str, StoryParagraph] = {p.scene_id: p for p in (paragraphs or [])}

    for char in characters:
        char_shots = [s for s in shots if char.id in s.characters]
        if not char_shots:
            continue

        actions = [
            s.visual_prompts.action_prompt or s.action_summary
            for s in char_shots[:5]
        ]
        combined = " then ".join(actions)

        if paragraphs:
            # Build curve from paragraph emotions
            raw_curve = [
                EMOTION_INTENSITY.get(
                    para_map.get(s.scene_id, StoryParagraph("", "", "", "", "", "action", "", "", False)).emotion,
                    0.5,
                )
                for s in char_shots
            ]
            intensity = _smooth_curve(raw_curve)
        else:
            # Fallback: original oscillating pattern
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
