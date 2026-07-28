"""
Script & Motion API Endpoints
REST endpoints for pre-production script splitting workflow.

Provides:
  POST /api/aicss/v2/scripts/parse                          — Two-pass script normalization + parse
  POST /api/aicss/v2/scripts/shots                          — Generate shot storyboard
  POST /api/aicss/v2/scripts/scene-prompts                  — Get structured scene prompts
  POST /api/aicss/v2/scripts/action-sequences               — Get character action sequences
  POST /api/aicss/v2/scripts/visual-prompt                  — Generate visual prompt only
  POST /api/aicss/v2/scripts/characters/generate-three-view  — Generate three-view reference
  POST /api/aicss/v2/scripts/characters/generate-variation   — Generate character variation
  POST /api/aicss/v2/scripts/motion/generate                 — Full motion pipeline
  POST /api/aicss/v2/scripts/motion/extract-frames          — Extract PNG frames from video
  POST /api/aicss/v2/scripts/motion/segment                  — Segment person from frames

Reference: docs/API_PROTOCOL_v2.md Section 8 (Script & Motion workflow)
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.script_parser import (
    ScriptData,
    Character,
    ScriptLanguage,
    StoryParagraph,
    normalize_script,
    parse_script,
    extract_characters,
    serialize_script_data,
    deserialize_script_data,
)
from app.services.shot_generator import (
    Shot,
    generate_shots,
    generate_scene_transitions,
    generate_character_action_sequences,
    serialize_shots,
)
from app.services.character_generator import (
    CharacterAsset,
    CharacterVariation,
    generate_visual_prompt,
    generate_character_reference,
    generate_character_three_view,
    generate_character_variation,
    build_character_asset,
    serialize_character_asset,
)
from app.services.auto_three_view import (
    kickoff_after_parse,
    get_progress as get_auto_three_view_progress,
    clear_progress as clear_auto_three_view_progress,
)
from app.services.auto_scene_view import (
    kickoff_after_parse as kickoff_scene_after_parse,
    get_progress as get_auto_scene_progress,
    clear_progress as clear_auto_scene_progress,
)
from app.services.scene_generator import (
    SceneAsset as SceneAssetModel,
    generate_scene_keyframes,
    generate_scene_visual_prompt,
    build_scene_asset,
    serialize_scene_asset,
)
from app.services.motion_extractor import (
    MotionSequence,
    SegmentedFrame,
    generate_action_video,
    extract_frames_from_video,
    segment_frames_sequence,
    serialize_motion_sequence,
)
from app.services.project_store import project_store

logger = logging.getLogger("aicss")

router = APIRouter(prefix="/v2/scripts", tags=["Script & Motion"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class ParseScriptRequest(BaseModel):
    raw_text: str = Field(..., description="Raw script text")
    language: str = Field(default="chinese", description="chinese, english, japanese")
    project_id: Optional[str] = Field(default=None, description="Optional project ID for persistence")


class ParseScriptResponse(BaseModel):
    normalized_script: str
    script_data: dict
    project_id: Optional[str] = None


class ExtractCharactersRequest(BaseModel):
    raw_text: str = Field(..., description="Raw script text")
    language: str = Field(default="chinese", description="chinese, english, japanese")
    project_id: Optional[str] = Field(default=None, description="Optional project ID for persistence")


class ExtractCharactersResponse(BaseModel):
    characters: list[dict] = Field(default_factory=list)
    project_id: Optional[str] = None


class GenerateShotsRequest(BaseModel):
    script_data: dict = Field(..., description="Serialized ScriptData from parse step")
    shots_per_scene: int = Field(default=4, ge=1, le=12,
                                description="Lower bound per scene. Total shot count is also "
                                            "driven by story_paragraph count — see /shots endpoint doc.")
    language: Optional[str] = None
    project_id: Optional[str] = None


class GenerateShotsResponse(BaseModel):
    shots: list[dict]
    scene_transitions: list[dict]
    character_action_sequences: list[dict]
    total_duration_seconds: float
    project_id: Optional[str] = None


class ScenePromptsRequest(BaseModel):
    shots: list[dict]
    project_id: Optional[str] = None


class ScenePromptsResponse(BaseModel):
    scene_prompts: list[dict]  # per-shot structured prompts
    transition_prompts: list[dict]


class ActionSequencesRequest(BaseModel):
    shots: list[dict]
    characters: list[dict]
    paragraphs: Optional[list[dict]] = None
    project_id: Optional[str] = None


class ActionSequencesResponse(BaseModel):
    sequences: list[dict]


class VisualPromptRequest(BaseModel):
    character_name: str
    gender: str = ""
    age: str = ""
    personality: str = ""
    genre: str = "cinematic"
    language: str = "chinese"


class GenerateThreeViewRequest(BaseModel):
    character_id: str
    character_name: str
    character_gender: str = ""
    character_age: str = ""
    character_personality: str = ""
    visual_prompt: Optional[str] = None
    reference_image: Optional[str] = Field(default=None, description="Base64 or URL")
    project_id: Optional[str] = None


class ThreeViewResponse(BaseModel):
    character_id: str
    visual_prompt: str
    three_view_images: dict[str, Optional[str]]  # front/side/back -> base64 or None
    reference_image: Optional[str] = None
    project_id: Optional[str] = None


class GenerateVariationRequest(BaseModel):
    character_id: str
    variation_prompt: str
    reference_image: Optional[str] = None
    project_id: Optional[str] = None


class VariationResponse(BaseModel):
    character_id: str
    variation_id: str
    variation_prompt: str
    image: Optional[str] = None
    project_id: Optional[str] = None


class GenerateMotionRequest(BaseModel):
    shot_id: str
    character_id: str
    character_name: str
    action_prompt: str
    start_image: Optional[str] = Field(default=None, description="Base64 start frame")
    end_image: Optional[str] = Field(default=None, description="Base64 end frame")
    duration_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    video_provider: str = Field(
        default="dashscope",
        description="Video provider: dashscope | local_wan | svd",
    )
    project_id: Optional[str] = None


class MotionResponse(BaseModel):
    shot_id: str
    character_id: str
    status: str
    video_path: Optional[str] = None
    frame_count: int = 0
    segmented_frames: list[dict] = []
    project_id: Optional[str] = None


class ExtractFramesRequest(BaseModel):
    video_path: str
    output_dir: Optional[str] = None
    fps: float = 30.0
    max_frames: int = 300
    project_id: Optional[str] = None


class ExtractFramesResponse(BaseModel):
    frame_paths: list[str]
    frame_count: int


class SegmentFramesRequest(BaseModel):
    frame_paths: list[str]
    character_name: str
    action_name: str
    output_dir: Optional[str] = None
    project_id: Optional[str] = None


class SegmentFramesResponse(BaseModel):
    segmented_frames: list[dict]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lang_from_str(lang_str: str) -> ScriptLanguage:
    """Map a language string to ScriptLanguage enum (case-insensitive)."""
    mapping = {
        "chinese": ScriptLanguage.CHINESE,
        "english": ScriptLanguage.ENGLISH,
        "japanese": ScriptLanguage.JAPANESE,
    }
    return mapping.get(lang_str.lower(), ScriptLanguage.CHINESE)


# ─────────────────────────────────────────────────────────────────────────────
# Script Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/parse", response_model=ParseScriptResponse)
async def api_normalize_and_parse(request: ParseScriptRequest):
    """
    Script processing with optional normalize + parallel parse.

    The /parse endpoint used to be a strict 2-pass flow (always normalize
    first, then parse). For scripts that already follow standard screenplay
    conventions ("内景 X - 时间", "EXT. X - TIME" headings), the normalize
    step is now skipped — the regex-based skip check looks at the first 200
    non-empty lines for at least one recognised scene heading.

    Pass 2 (parse) runs FOUR LLM calls in parallel:
      - header   (title / genre / logline)
      - scenes   (scene list)
      - characters (via existing Pass 1.5)
      - paragraphs (depends on scene_count, runs after scenes)
    Any sub-task failure only degrades that field; the rest stay populated.
    """
    lang = _lang_from_str(request.language)
    raw = request.raw_text

    # ── Skip normalize when the script already looks standardised ───────────
    def _looks_normalised(text: str) -> bool:
        """True if at least one scene heading is found in the first 200 lines."""
        import re as _re
        head_re = _re.compile(
            r"^\s*(?:(?:内|外)景\s*.+?\s*[-—]\s*(?:日|夜|黎明|清晨|傍晚|黄昏|夜晚|白天|昼)"
            r"|INT\.|EXT\.)",
            _re.M,
        )
        lines = [l for l in text.splitlines() if l.strip()][:200]
        return any(head_re.match(l) for l in lines)

    if _looks_normalised(raw):
        normalized = raw
        logger.info("[script] normalize skipped (input already in screenplay form)")
    else:
        normalized = await normalize_script(raw, lang)

    # Pass 2: Parallel parse (4 LLM calls fired concurrently)
    script_data = await parse_script(normalized, lang)

    project_id = request.project_id
    serialized = serialize_script_data(script_data)

    # Save to project store if project_id provided
    if project_id:
        try:
            await project_store.save_script_data(project_id, serialized)
        except Exception as e:
            logger.warning(f"[script] Failed to persist script data: {e}")

        # ── Auto-batch: kick off three-view generation for every detected
        # character (fire-and-forget; progress polled via /characters/batch-status).
        try:
            await kickoff_after_parse(
                project_id=project_id,
                characters=script_data.characters,
                genre=script_data.genre or "cinematic",
                language=lang,
            )
        except Exception as e:
            logger.warning(f"[script] Failed to kick off auto three-view: {e}")

        # ── Auto-batch: kick off scene keyframe generation (wide/closeup/mood)
        try:
            await kickoff_scene_after_parse(
                project_id=project_id,
                scenes=script_data.scenes,
                genre=script_data.genre or "cinematic",
                language=lang,
            )
        except Exception as e:
            logger.warning(f"[script] Failed to kick off auto scene assets: {e}")

    return ParseScriptResponse(
        normalized_script=normalized,
        script_data=serialized,
        project_id=project_id,
    )


@router.post("/characters/extract", response_model=ExtractCharactersResponse)
async def api_extract_characters(request: ExtractCharactersRequest):
    """
    Character-first extraction: identify all real human characters in the script.

    This is Pass 1.5 of the character-first pipeline. Runs an LLM call
    focused exclusively on character identification (no scenes, no paragraphs),
    then falls back to heuristic bracket/dialogue detection when the LLM is
    unavailable.

    The returned characters can be passed back into the shot generation
    pipeline as a curated, character-grounded input — preventing scene/shot
    generators from inheriting pseudo-character noise ("特写", "异常出现", etc.).
    """
    lang = _lang_from_str(request.language)
    characters = await extract_characters(request.raw_text, lang)
    # ``extract_characters`` always returns Character dataclasses (or empty
    # list), so map them to dicts here.
    char_dicts = [c.to_dict() if hasattr(c, "to_dict") else c for c in characters]

    project_id = request.project_id
    if project_id:
        try:
            await project_store.save_characters(project_id, char_dicts)
        except Exception as e:
            logger.warning(f"[script] Failed to persist characters: {e}")

    return ExtractCharactersResponse(
        characters=char_dicts,
        project_id=project_id,
    )


@router.post("/shots", response_model=GenerateShotsResponse)
async def api_generate_shots(request: GenerateShotsRequest):
    """
    Generate shot storyboard from parsed script data.

    Produces Shot objects with camera movement, shot size, visual prompts and
    per-character action sequences. Saves to the project store when a
    project_id is provided.
    """
    # Reconstruct ScriptData
    script_data = deserialize_script_data(request.script_data)

    # Override language if specified
    lang = _lang_from_str(request.language) if request.language else script_data.language

    # Generate shots
    shots = await generate_shots(script_data, request.shots_per_scene, lang)
    scene_transitions = generate_scene_transitions(shots)
    action_sequences = generate_character_action_sequences(
        shots, script_data.characters, script_data.story_paragraphs
    )

    total_duration = sum(s.duration_seconds for s in shots)

    serialized_shots = serialize_shots(shots)

    # Serialize action sequences
    serialized_sequences = [
        {
            "character_id": seq.character_id,
            "character_name": seq.character_name,
            "shots": seq.shots,
            "action_sequence_prompt": seq.action_sequence_prompt,
            "intensity_curve": seq.intensity_curve,
        }
        for seq in action_sequences
    ]

    # Serialize transitions
    serialized_transitions = [
        {
            "from_scene_id": t.from_scene_id,
            "to_scene_id": t.to_scene_id,
            "transition_type": t.transition_type,
            "transition_prompt": t.transition_prompt,
        }
        for t in scene_transitions
    ]

    # Save shots to project store if project_id provided
    project_id = request.project_id
    if project_id:
        try:
            await project_store.save_shot_list(project_id, serialized_shots)
        except Exception as e:
            logger.warning(f"[script] Failed to persist shot list: {e}")

    return GenerateShotsResponse(
        shots=serialized_shots,
        scene_transitions=serialized_transitions,
        character_action_sequences=serialized_sequences,
        total_duration_seconds=total_duration,
        project_id=project_id,
    )


@router.post("/scene-prompts", response_model=ScenePromptsResponse)
async def api_get_scene_prompts(request: ScenePromptsRequest):
    """
    Get structured scene and transition prompts from a shot list.

    Useful when the frontend already has a shot list (e.g. from a previous
    /shots call) but needs only the structured prompts to drive image
    generation.
    """
    from app.services.shot_generator import _build_shots_from_json

    empty_script = ScriptData()
    shots = _build_shots_from_json(request.shots, empty_script)
    scene_transitions = generate_scene_transitions(shots)

    scene_prompts = [
        {
            "shot_id": s.id,
            "scene_id": s.scene_id,
            "shot_number": s.shot_number,
            "scene_prompt": s.visual_prompts.scene_prompt,
            "action_prompt": s.visual_prompts.action_prompt,
            "camera_prompt": s.visual_prompts.camera_prompt,
            "transition_prompt": s.visual_prompts.transition_prompt,
            "duration_seconds": s.duration_seconds,
        }
        for s in shots
    ]

    transition_prompts = [
        {
            "from_scene_id": t.from_scene_id,
            "to_scene_id": t.to_scene_id,
            "transition_type": t.transition_type,
            "transition_prompt": t.transition_prompt,
        }
        for t in scene_transitions
    ]

    return ScenePromptsResponse(
        scene_prompts=scene_prompts,
        transition_prompts=transition_prompts,
    )


@router.post("/action-sequences", response_model=ActionSequencesResponse)
async def api_get_action_sequences(request: ActionSequencesRequest):
    """
    Get character action sequences across all shots.

    Builds CharacterActionSequence objects describing each character's
    shot-to-shot motion and an intensity curve.
    """
    from app.services.shot_generator import _build_shots_from_json

    shots = _build_shots_from_json(request.shots, ScriptData())

    characters = [
        Character(
            id=c.get("id", c.get("character_id", "")),
            name=c.get("name", ""),
            gender=c.get("gender", ""),
            age=c.get("age", ""),
            personality=c.get("personality", ""),
        )
        for c in request.characters
    ]

    paragraphs = None
    if request.paragraphs:
        paragraphs = [
            StoryParagraph(
                id=p.get("id", ""),
                text=p.get("text", ""),
                scene_ref_id=p.get("scene_ref_id", p.get("sceneRefId", "")),
                paragraph_type=p.get("paragraph_type", "action"),
                speaker_id=p.get("speaker_id", ""),
                emotion=p.get("emotion", ""),
                contains_action=p.get("contains_action", True),
            )
            for p in request.paragraphs
        ]

    sequences = generate_character_action_sequences(shots, characters, paragraphs)

    serialized = [
        {
            "character_id": seq.character_id,
            "character_name": seq.character_name,
            "shots": seq.shots,
            "action_sequence_prompt": seq.action_sequence_prompt,
            "intensity_curve": seq.intensity_curve,
        }
        for seq in sequences
    ]

    return ActionSequencesResponse(sequences=serialized)


@router.post("/visual-prompt")
async def api_generate_visual_prompt(request: VisualPromptRequest):
    """
    Generate visual prompt for a character without producing images.

    Useful for previewing prompts before committing to expensive image
    generation.
    """
    char = Character(
        id="temp",
        name=request.character_name,
        gender=request.gender,
        age=request.age,
        personality=request.personality,
    )
    prompt = await generate_visual_prompt(
        char,
        genre=request.genre,
        language=_lang_from_str(request.language),
    )
    return {"visual_prompt": prompt}


# ─────────────────────────────────────────────────────────────────────────────
# Character Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/characters/generate-three-view", response_model=ThreeViewResponse)
async def api_generate_three_view(request: GenerateThreeViewRequest):
    """
    Generate three-view character reference images.

    Produces front / side / back images for character consistency across shots,
    plus a base reference image. Saves a CharacterAsset JSON to the project
    store when a project_id is provided.
    """
    character = Character(
        id=request.character_id,
        name=request.character_name,
        gender=request.character_gender,
        age=request.character_age,
        personality=request.character_personality,
        visual_prompt=request.visual_prompt or "",
    )

    # Generate visual prompt if not provided
    if not character.visual_prompt:
        character.visual_prompt = await generate_visual_prompt(character)

    # Generate three-view images
    three_view_images = await generate_character_three_view(
        character,
        character.visual_prompt,
    )

    # Resolve reference image: explicit input wins, else auto-generate
    if request.reference_image:
        reference_image = request.reference_image
    else:
        reference_image = await generate_character_reference(character, character.visual_prompt)

    # Save to project store
    asset = build_character_asset(character, reference_image, three_view_images)
    project_id = request.project_id
    if project_id:
        try:
            await project_store.save_character_asset(
                project_id,
                request.character_id,
                payload=serialize_character_asset(asset),
            )
        except Exception as e:
            logger.warning(f"[script] Failed to persist character asset: {e}")

    return ThreeViewResponse(
        character_id=request.character_id,
        visual_prompt=character.visual_prompt,
        three_view_images=three_view_images,
        reference_image=reference_image,
        project_id=project_id,
    )


@router.post("/characters/generate-variation", response_model=VariationResponse)
async def api_generate_variation(request: GenerateVariationRequest):
    """
    Generate character wardrobe / outfit variation.

    Persists the variation to the project's characters/<id>.json store when a
    project_id is provided.
    """
    variation_id = f"var-{uuid.uuid4().hex[:8]}"

    image = await generate_character_variation(
        Character(id=request.character_id, name=""),
        request.variation_prompt,
        reference_image_b64=request.reference_image,
    )

    project_id = request.project_id
    if project_id:
        try:
            await project_store.add_character_variation(
                project_id,
                request.character_id,
                {
                    "id": variation_id,
                    "name": request.variation_prompt[:50],
                    "visual_prompt": request.variation_prompt,
                    "image": image,
                },
            )
        except Exception as e:
            logger.warning(f"[script] Failed to persist variation: {e}")

    return VariationResponse(
        character_id=request.character_id,
        variation_id=variation_id,
        variation_prompt=request.variation_prompt,
        image=image,
        project_id=project_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auto Three-View Batch Status (polled by frontend after /parse)
# ─────────────────────────────────────────────────────────────────────────────

class BatchStatusEntry(BaseModel):
    name: str
    status: str                # queued | running | done | failed
    started_at: float = 0.0
    finished_at: Optional[float] = None
    error: Optional[str] = None
    visual_prompt: Optional[str] = None
    asset: Optional[dict] = None


class BatchStatusResponse(BaseModel):
    project_id: str
    characters: dict[str, BatchStatusEntry]
    summary: dict              # {queued, running, done, failed}


@router.get("/characters/batch-status", response_model=BatchStatusResponse)
async def api_batch_status(project_id: str):
    """
    Poll this from the frontend after /parse returns. Tells the UI which
    characters have their three-view assets ready.
    """
    raw = get_auto_three_view_progress(project_id)
    summary = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for entry in raw.values():
        summary[entry.get("status", "queued")] = summary.get(entry.get("status", "queued"), 0) + 1
    return BatchStatusResponse(
        project_id=project_id,
        characters={k: BatchStatusEntry(**v) for k, v in raw.items()},
        summary=summary,
    )


@router.post("/characters/batch-clear", response_model=dict)
async def api_batch_clear(project_id: str):
    """Drop the in-memory progress table for a project (e.g. on project delete)."""
    clear_auto_three_view_progress(project_id)
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Scene Asset Endpoints (auto batch + manual)
# ─────────────────────────────────────────────────────────────────────────────

class GenerateSceneAssetRequest(BaseModel):
    scene_id: str
    location: str
    time: str = "Day"
    atmosphere: str = ""
    visual_prompt: Optional[str] = None
    reference_image: Optional[str] = None
    project_id: Optional[str] = None


class SceneAssetResponse(BaseModel):
    scene_id: str
    visual_prompt: str
    keyframe_images: dict[str, str]      # wide/closeup/mood -> base64
    project_id: Optional[str] = None


class SceneBatchStatusEntry(BaseModel):
    name: str
    status: str                          # queued | running | done | failed
    started_at: float = 0.0
    finished_at: Optional[float] = None
    error: Optional[str] = None
    visual_prompt: Optional[str] = None
    asset: Optional[dict] = None


class SceneBatchStatusResponse(BaseModel):
    project_id: str
    scenes: dict[str, SceneBatchStatusEntry]
    summary: dict


@router.post("/scenes/generate-asset", response_model=SceneAssetResponse)
async def api_generate_scene_asset(request: GenerateSceneAssetRequest):
    """Manual single-scene asset generation (3 keyframes)."""
    from app.services.script_parser import Scene
    scene = Scene(
        id=request.scene_id,
        location=request.location,
        time=request.time,
        atmosphere=request.atmosphere,
        visual_prompt=request.visual_prompt or "",
    )

    if not scene.visual_prompt:
        scene.visual_prompt = await generate_scene_visual_prompt(scene)

    keyframes = await generate_scene_keyframes(
        scene, visual_prompt=scene.visual_prompt,
        anchor_image=request.reference_image,
    )

    if request.project_id:
        try:
            asset = build_scene_asset(scene, keyframes)
            asset.visual_prompt = scene.visual_prompt
            await project_store.save_scene_asset(
                request.project_id, scene.id,
                payload=serialize_scene_asset(asset),
            )
        except Exception as e:
            logger.warning(f"[script] Failed to persist scene asset: {e}")

    return SceneAssetResponse(
        scene_id=request.scene_id,
        visual_prompt=scene.visual_prompt,
        keyframe_images=keyframes or {},
        project_id=request.project_id,
    )


@router.get("/scenes/batch-status", response_model=SceneBatchStatusResponse)
async def api_scene_batch_status(project_id: str):
    raw = get_auto_scene_progress(project_id)
    summary = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for entry in raw.values():
        s = entry.get("status", "queued")
        summary[s] = summary.get(s, 0) + 1
    return SceneBatchStatusResponse(
        project_id=project_id,
        scenes={k: SceneBatchStatusEntry(**v) for k, v in raw.items()},
        summary=summary,
    )


@router.post("/scenes/batch-clear", response_model=dict)
async def api_scene_batch_clear(project_id: str):
    clear_auto_scene_progress(project_id)
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Motion Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/motion/generate", response_model=MotionResponse)
async def api_generate_motion(request: GenerateMotionRequest):
    """
    Full motion sequence pipeline.

    Steps:
      1. Generate action video via DashScope (or other provider)
      2. Extract PNG frames via ffmpeg
      3. Segment person from frames via SAM2 (if available)

    Persists the resulting MotionSequence JSON to <project>/motions/<shot_id>.json
    when a project_id is provided.
    """
    from app.services.motion_extractor import generate_motion_sequence

    motion = await generate_motion_sequence(
        shot_id=request.shot_id,
        character_id=request.character_id,
        character_name=request.character_name,
        action_prompt=request.action_prompt,
        start_image_b64=request.start_image,
        end_image_b64=request.end_image,
        duration_seconds=request.duration_seconds,
        video_provider=request.video_provider,
    )

    # Collect segmented frame paths
    segmented_frames = []
    if motion.segmented_dir:
        from pathlib import Path
        for f in sorted(Path(motion.segmented_dir).glob("*.png")):
            segmented_frames.append({
                "frame_index": len(segmented_frames),
                "path": str(f),
                "filename": f.name,
            })

    project_id = request.project_id
    if project_id:
        try:
            await project_store.save_motion_sequence(
                project_id,
                request.shot_id,
                serialize_motion_sequence(motion),
            )
        except Exception as e:
            logger.warning(f"[script] Failed to persist motion sequence: {e}")

    return MotionResponse(
        shot_id=request.shot_id,
        character_id=request.character_id,
        status=motion.status,
        video_path=motion.video_path,
        frame_count=motion.frame_count,
        segmented_frames=segmented_frames,
        project_id=project_id,
    )


@router.post("/motion/extract-frames", response_model=ExtractFramesResponse)
async def api_extract_frames(request: ExtractFramesRequest):
    """
    Extract PNG frames from a video file using ffmpeg.
    """
    output_dir = request.output_dir or f"backend/.cache/frames/{uuid.uuid4().hex[:8]}"

    frames = extract_frames_from_video(
        request.video_path,
        output_dir,
        request.fps,
        request.max_frames,
    )

    return ExtractFramesResponse(
        frame_paths=frames,
        frame_count=len(frames),
    )


@router.post("/motion/segment", response_model=SegmentFramesResponse)
async def api_segment_frames(request: SegmentFramesRequest):
    """
    Segment the person from a list of frame paths using SAM2.
    """
    output_dir = request.output_dir or f"backend/.cache/segmented/{uuid.uuid4().hex[:8]}"

    try:
        from app.models import model_manager
        sam2 = model_manager.sam2 if model_manager.is_loaded() else None
    except Exception:
        sam2 = None

    if not sam2:
        raise HTTPException(status_code=503, detail="SAM2 model not loaded")

    segmented = segment_frames_sequence(
        request.frame_paths,
        output_dir,
        sam2,
        request.character_name,
        request.action_name,
    )

    return SegmentFramesResponse(
        segmented_frames=[
            {
                "frame_index": sf.frame_index,
                "original_path": sf.original_path,
                "segmented_path": sf.segmented_path,
                "character_name": sf.character_name,
                "action_name": sf.action_name,
                "success": bool(sf.segmented_path),
            }
            for sf in segmented
        ],
    )
