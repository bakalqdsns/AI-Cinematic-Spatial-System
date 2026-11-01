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
