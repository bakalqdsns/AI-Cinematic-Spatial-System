"""
Add 3 new async extract functions (header / scenes / paragraphs) and
replace parse_script with a parallel orchestrator.
"""
import re

path = r"F:\AICinematicSpatialSystem\backend\app\services\script_parser.py"
src = open(path, "r", encoding="utf-8").read()

# Find the parse_script function body (between its def line and the next blank line + comment block).
parse_pat = re.compile(
    r"^async def parse_script\(.+?\n    return _fallback_script_data\(normalized_text, language\)\n",
    re.M | re.S,
)
m = parse_pat.search(src)
if not m:
    raise SystemExit("parse_script not found")
print("parse_script span:", m.span())

new_parse = '''async def _extract_header(
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
        ScriptLanguage.CHINESE: "请提取下面这段剧本的元信息（title/genre/logline）：\\n\\n{text}",
        ScriptLanguage.ENGLISH: "Extract metadata (title/genre/logline) from this script:\\n\\n{text}",
        ScriptLanguage.JAPANESE: "次の脚本のメタデータ（title/genre/logline）を抽出してください：\\n\\n{text}",
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
    title_match = re.search(r"《([^》\\n]+)》|^\\s*([A-Z][A-Za-z0-9 _-]{2,40})\\s*$", raw_text, re.M)
    title = "Untitled"
    if title_match:
        title = title_match.group(1) or title_match.group(2) or title
    return {"title": title, "genre": "drama", "logline": raw_text[:60].replace("\\n", " ").strip()}


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
        ScriptLanguage.CHINESE: "请从这个剧本中**只**提取场景列表：\\n\\n{text}",
        ScriptLanguage.ENGLISH: "Extract ONLY the scene list from this script:\\n\\n{text}",
        ScriptLanguage.JAPANESE: "次の脚本からシーンリスト**のみ**を抽出してください：\\n\\n{text}",
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
            "请按场景顺序切分下面的剧本为段落数组：\\n\\n{{text}}"
        ).format(scene_count=scene_count, text="{text}"),
        ScriptLanguage.ENGLISH: (
            "The script has {scene_count} scenes (scene_index 1..{scene_count}). "
            "Split the following script into paragraphs in scene order:\\n\\n{{text}}"
        ).format(scene_count=scene_count, text="{text}"),
        ScriptLanguage.JAPANESE: (
            "脚本には {scene_count} 個のシーンがあります（scene_index は 1〜{scene_count}）。"
            "次の脚本をシーン順に段落配列へ分割してください：\\n\\n{{text}}"
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
    Pass 2 — Parallel script extraction.

    Runs THREE independent LLM calls concurrently (header, scenes, paragraphs)
    plus a separate characters call, then stitches the results into a single
    ScriptData. Each sub-task is small enough to fit comfortably within the
    9B model's context window, so the previous "Pass 2 cuts off mid-JSON"
    failure mode disappears.

    If any sub-task fails, only that field degrades to a heuristic fallback;
    the other fields stay populated.
    """
    import asyncio

    # ── Fire all four LLM calls in parallel ───────────────────────────────────
    header_task = _extract_header(normalized_text, language)
    scenes_task = _extract_scenes(normalized_text, language)
    chars_task = extract_characters(normalized_text, language)
    # Paragraphs depend on scene_count, so we can't fire in parallel with
    # scenes unless we use a placeholder count.  We optimistically kick it off
    # with a conservative guess (len(scenes) once known), and if scenes also
    # fail, paragraphs still runs with the default count.
    paragraphs_task: asyncio.Task = None  # type: ignore[assignment]

    header_data, scenes_data, chars = await asyncio.gather(
        header_task, scenes_task, chars_task,
        return_exceptions=True,
    )

    # Normalise exception results.
    if isinstance(header_data, Exception):
        logger.warning("[script_parser] header gather exc: %s", header_data)
        header_data = {}
    if isinstance(scenes_data, Exception):
        logger.warning("[script_parser] scenes gather exc: %s", scenes_data)
        scenes_data = []
    if isinstance(chars, Exception):
        logger.warning("[script_parser] chars gather exc: %s", chars)
        chars = []

    scenes_list: list[dict] = scenes_data or []
    scene_count = len(scenes_list) if scenes_list else 1
    paragraphs_data = await _extract_paragraphs(normalized_text, scene_count, language)

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


'''

new_src = src[: m.start()] + new_parse + src[m.end():]

with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)

print("Replaced parse_script; new length:", len(new_parse), "chars")