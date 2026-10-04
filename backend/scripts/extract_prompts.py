# -*- coding: utf-8 -*-
"""提取所有需要多模态生成的资产提示词，输出清单"""
import json
from pathlib import Path

state = json.loads(Path(r"F:\AICinematicSpatialSystem\backend\.workspace\projects\20260927_055614_旧相册\pipeline_state.json").read_text(encoding="utf-8"))
script = state["script_data"]
shots = state["shots"]

out = []
out.append("# 人机协同测试 — 多模态资产生成清单\n")
out.append("项目：旧相册（2 角色 × 2 场景 × 14 镜头）\n")
out.append("说明：以下提示词需你用外部工具（MJ/即梦/可灵等）生成图/视频，")
out.append("生成后放到指定路径，pipeline 即可跳过多模态调用直接跑后续步骤。\n\n")

# ── 角色 ──
out.append("## 一、角色三视图（6 张图）\n")
out.append("每角色 3 视图：front / side / back。建议先生成 front，再用 front 做 img2img 生成 side/back。\n\n")
for ch in script["characters"]:
    cid = ch["id"]
    name = ch["name"]
    gender = ch.get("gender","")
    personality = ch.get("personality","")
    out.append(f"### {name}（{cid}）\n")
    out.append(f"- 性别: {gender}\n- 性格: {personality}\n")
    out.append(f"- 剧本线索: 李明穿浅灰衬衫肩挎帆布包；张华穿深蓝毛衣手提深蓝丝带礼盒\n\n")
    base = f"{name}, male, {personality}"
    out.append("**front.png** (正面角色表):\n")
    out.append("```\n")
    out.append(f"{base}, character sheet, front view, facing camera, neutral pose, full body, white background, concept art, anime style, high detail\n")
    out.append("```\n")
    out.append("**side.png** (侧面，img2img from front):\n")
    out.append("```\n")
    out.append(f"{base}, side profile view, 90 degree angle, full body, same character, same outfit, same art style, white background\n")
    out.append("```\n")
    out.append("**back.png** (背面，img2img from front):\n")
    out.append("```\n")
    out.append(f"{base}, back view, from behind, full body, same character, same outfit, same art style, white background\n")
    out.append("```\n")
    out.append(f"输出路径: characters/{name}/three_view/front.png | side.png | back.png\n\n")

# ── 场景 ──
out.append("## 二、场景三关键帧（6 张图）\n")
out.append("每场景 3 视图：wide / closeup / mood。建议先生成 wide，再用 wide 做 img2img 生成 closeup/mood。\n\n")
for sc in script["scenes"]:
    sid = sc["id"]
    loc = sc["location"]
    time = sc.get("time","")
    atm = sc.get("atmosphere","")
    # 从 shots 找该场景的 scene_prompt
    scene_prompt = ""
    for s in shots:
        if s.get("scene_id") == sid:
            scene_prompt = (s.get("visual_prompts") or {}).get("scene_prompt","")
            break
    out.append(f"### {loc}（{sid}）\n")
    out.append(f"- 时间: {time} | 氛围: {atm}\n")
    out.append(f"- LLM 生成的 scene_prompt: {scene_prompt}\n\n")
    base = scene_prompt or f"{loc}, {time}, {atm}, cinematic style"
    out.append("**wide.png** (远景建立镜头):\n")
    out.append("```\n")
    out.append(f"{base}, wide establishing shot, full location visible, cinematic composition, no people, no characters, empty scene, concept art background, high detail, dramatic lighting\n")
    out.append("```\n")
    out.append("**closeup.png** (特写细节，img2img from wide):\n")
    out.append("```\n")
    out.append(f"{base}, close-up detail, focus on a striking prop or texture, shallow depth of field, same art style, same palette\n")
    out.append("```\n")
    out.append("**mood.png** (氛围镜头，img2img from wide):\n")
    out.append("```\n")
    out.append(f"{base}, atmospheric mood shot, ambient light and shadow, silhouette only, empty foreground, focus on color and tone, same art style, same palette\n")
    out.append("```\n")
    out.append(f"输出路径: scenes/{loc}/wide.png | closeup.png | mood.png\n\n")

# ── 动作视频 ──
out.append("## 三、角色动作视频（14 个 shot，每个 1 个视频）\n")
out.append("每个 shot 用角色 front.png 做起始帧 + action_prompt 生成 5 秒视频。\n")
out.append("视频生成后放到 motions/<角色名>/<action_slug>/frame_000.png ... frame_023.png（24 帧）\n")
out.append("或直接放 mp4，我写脚本帮你转帧序列。\n\n")
for s in shots:
    sid = s["id"]
    vp = s.get("visual_prompts") or {}
    action = vp.get("action_prompt","") or s.get("action_summary","")
    chars = s.get("characters",[])
    dur = s.get("duration_seconds", 5.0)
    out.append(f"### {sid}（{dur}秒，角色: {','.join(chars)}）\n")
    out.append(f"- action_summary: {s.get('action_summary','')}\n")
    out.append(f"- dialogue: {s.get('dialogue','')[:80]}\n")
    out.append(f"- 起始帧: 用对应角色的 front.png\n")
    out.append(f"- **action_prompt**:\n```\n{action}\n```\n\n")

Path(r"F:\AICinematicSpatialSystem\backend\scripts\human_loop_prompts.md").write_text("".join(out), encoding="utf-8")
print("written: scripts/human_loop_prompts.md")
print(f"chars: {len(script['characters'])}, scenes: {len(script['scenes'])}, shots: {len(shots)}")
