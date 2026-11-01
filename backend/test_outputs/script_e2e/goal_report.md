# 开题报告目标与当前差距

## 目标成片

开题报告要的是一段 4–5 分钟、1080p 的 2.5D 纸雕空间动画《纸间行》。人物是白衣少女，场景和人物都用纸雕质感，纸雕质感统一。链路是剧本分镜、场景和人物三视图、GroundingDINO 加 SAM2 分割、Depth-Anything-V2 深度、遮挡补全、分层卡片、Blender 搭建和 Cycles 渲染、人物绿幕动作合成。镜头动起来时，近处偏移大、远处偏移小；人物挡住的东西被 LaMa 补全；同一个人物在不同分镜里长得一样。

## 当前结果

- 场景出图是纸雕操场，方向正确。
- 动作视频和三视图都回到绿幕。三视图背景是纯亮绿；动作视频背景是暗绿带绿地板，不是平整的 #00FF00，但已经是绿幕。
- 抠像把绿幕背景抠掉了。`frame_0001.png` 红底验证：女孩剪影保留，边缘干净。
- 成片里人物已能站在场景中，但人物和场景的光照、色调、比例还没有完全统一；绿幕地板在动作视频里仍是一块深绿。

## 反复迭代的顺序

1. 先修人物素材：剧本和人物提示词锁到《纸间行》的白衣少女，动作视频只出平整绿幕。观察人物卡片边缘和衣服上有没有绿边或洞。
2. 再修人物和场景的一致性：把抠好的人物放进场景，观察它是不是和场景颜色、光照、比例对得上。
3. 再修分层和透视：三视图观察远处面片有没有被透视压扁，近处有没有挡住该挡住的东西。
4. 最后扩成片：多个分镜连起来，观察人物是不是在不同分镜里长得一样，动作有没有断。

每一轮都从成片或三视图倒推问题，改完再渲。

## 第 1 轮：素材锁定

- 已把端到端剧本改回《纸间行》的白衣少女和纸雕操场。
- 已把三视图写死的 `white background` 改成和绿幕后缀一致的亮绿。
- 证据：三视图现在是绿底；动作视频背景也是绿的，但偏暗、带绿地板。
- 新问题：动作视频的绿幕不是平整的 #00FF00，而是暗绿加绿地板。抠像仍把背景去掉了，但人物边缘的暗绿残留和动作视频里地板区域还需要再看。

## 第 2 轮：绿幕平整

证据：

- `char_front.png` 背景是纯亮绿 #00FF00，人物是《纸间行》的白衣少女，符合目标。
- 动作视频 `backend/.cache/comfy/minimax_8bf9eb2d.mp4` 背景是暗绿，地板是更深的绿条，不是平整的纯色绿幕。证据帧 `_evidence_video2_frame1.png` 和 `_evidence_video2_mid.png` 首帧、中间帧都如此。
- 抠像后 `_evidence_frame0001_on_red.png` 红底上人物剪影清楚，但源视频绿幕不够平整，说明绿幕提示词还不够硬。

改动：

- `backend/app/services/video_adapter.py`：`_comfy_greenscreen_prompt` 在原有固定后缀结构（`_apply_greenscreen_prompt` 后缀 + 人物锁定句）中间插入一句共享的 `_FLAT_CYCLORAMA_CLAUSE`，明确背景是一块平整的 bright green #00FF00 cyclorama，地面和背景是同一块绿色，no shadows、no gradient、no other colors or objects。
- `backend/app/services/character_generator.py`：`_comfy_character_prompt` 复用同一句 `_FLAT_CYCLORAMA_CLAUSE`，人物静帧和动作视频的平整措辞不再各自漂移。
- 动作提示词生成、分层、透视、模型名均未改动。
- 测试：`backend/test_greenscreen.py` 更新绿幕断言（cyclorama 现在必须出现），新增 `backend/tests/test_greenscreen_prompt.py` 断言 no shadows、no gradient、floor is the same green。

下一步：用收紧后的提示词重出一条动作视频，观察背景是否变成平整的 #00FF00、地板绿条是否消失，再重新抽帧抠像看人物边缘。

## 第 3 轮：动作视频验证

观察：

- 收紧后的动作视频 `minimax_2977bfa2.mp4` 背景仍是暗绿带深绿地板（`_evidence_video3_frame1.png`、`_evidence_video3_mid.png`），提示词收紧没有让 MiniMax 把绿幕画成平整亮绿。
- 但抠像反而更好：`frame_0001.png` 透明像素占 79%，`transparent_ratio: 0.79`，比之前 0% 和 30.5% 都好。绿幕背景基本被去掉。
- 成片 `render_mid.png` 里人物已经站在操场上，没有再带一块不透明卡片。

结论：MiniMax 本身画不出平整亮绿，但「边缘连通幕布采样」的抠像能容忍暗绿，把幕布去掉。当前人物合成已经成立。下一个差距是人物与场景的光照、比例和动作自然度，以及从单分镜扩到多分镜。

## 第 4 轮：分层明显化

观察：

- 三视图 `three_views/front.png` 里五层只是按深度缩放，正面完全重叠成一张平图，看不到纸片之间的缝，纸雕感不强。
- side/top 视角只能看到面片切线，层片全是零厚度平面，没有厚度、没有切边，层与层的错落全靠想象。
- 三视图只有 front/side/top 三个角度，没有能看到分层层次的 3/4 视角，也没有把层拆开看的视图。

改动（只动分层在 Blender 里的呈现，人物、动作、绿幕、场景类识别、深度归层语义都没动）：

- `backend/app/services/layer_exporter.py`：新增每层纸雕呈现参数 `LAYER_THICKNESS_M`（厚度 0.06–0.12m）、`LAYER_YAW_DEG`（同向偏航 2.0–2.5°）、`LAYER_PITCH_DEG`（俯仰 1.0–1.5°）、`LAYER_SHIFT_X_M` / `LAYER_SHIFT_Y_M`（水平错位 ±0.45m 内），并写进 `perspective_offsets` 和 `build_z_offset_table` 的每一行。`zOffset` 仍等于 `-depthMeters`，最近层 `scale` 仍是 1，归层语义不变。
- `backend/blender/addons/aicss_scene_builder/utils/scene_utils.py`：镜像同一份默认值，新增 `layer_thickness` / `layer_yaw_deg` / `layer_pitch_deg` / `layer_shift` 读取函数——清单里写了按清单，缺失或越界（厚度 0、偏航 60° 之类）回退默认。
- `backend/blender/addons/aicss_scene_builder/materials/paper_material.py`：新增 `apply_paper_edge_material`——所有层片共用一份暖纸板色「切边」材质，追加成独立材质槽。
- `backend/blender/addons/aicss_scene_builder/operators/import_layers.py`：层片按清单加错位和偏航/俯仰；缩放烘进网格后新增 `_add_card_thickness`——Solidify 沿背面挤出厚度（offset=-1，正面位置不动），挤出的 rim 面用切边材质，再加小 Bevel 让切边吃光。人物平面不动。
- `backend/blender/addons/aicss_scene_builder/utils/view_presets.py`（新）：纯 Python 视角预设，`VIEW_NAMES = front / side / top / front_three_quarter / layer_separation / exploded`，附各视角相机摆位和拆解布局 `exploded_x_offsets`（层片沿 X 单调拉开、中间层不动）。
- `backend/test_outputs/script_e2e/render_three_views.py`：改用 view_presets，六个视角都出图；渲 exploded 前把层片沿 X 拉开、按实际宽度拉远相机，渲完恢复原位。
- `backend/tests/test_layer_perspective.py`（新）：断言透视表带呈现字段且深度语义不变、插件默认值与后端一致、视角列表含 3/4 视角和拆解视图、拆解布局单调错开、切边材质和加厚接好。

下一步：重跑 `render_three_views.py` 和归档渲染，观察六个视角里切边和错位是否让五层在静止帧里也能分清，成片运镜时层间缝是否可见。
