# 人机协同测试 — 多模态资产生成清单
项目：旧相册（2 角色 × 2 场景 × 14 镜头）
说明：以下提示词需你用外部工具（MJ/即梦/可灵等）生成图/视频，生成后放到指定路径，pipeline 即可跳过多模态调用直接跑后续步骤。

## 一、角色三视图（6 张图）
每角色 3 视图：front / side / back。建议先生成 front，再用 front 做 img2img 生成 side/back。

### 李明（char-1）
- 性别: male
- 性格: 守时、略带焦虑，重情谊
- 剧本线索: 李明穿浅灰衬衫肩挎帆布包；张华穿深蓝毛衣手提深蓝丝带礼盒

**front.png** (正面角色表):
```
李明, male, 守时、略带焦虑，重情谊, character sheet, front view, facing camera, neutral pose, full body, white background, concept art, anime style, high detail
```
**side.png** (侧面，img2img from front):
```
李明, male, 守时、略带焦虑，重情谊, side profile view, 90 degree angle, full body, same character, same outfit, same art style, white background
```
**back.png** (背面，img2img from front):
```
李明, male, 守时、略带焦虑，重情谊, back view, from behind, full body, same character, same outfit, same art style, white background
```
输出路径: characters/李明/three_view/front.png | side.png | back.png

### 张华（char-2）
- 性别: male
- 性格: 热情、歉意感强，怀旧而温暖
- 剧本线索: 李明穿浅灰衬衫肩挎帆布包；张华穿深蓝毛衣手提深蓝丝带礼盒

**front.png** (正面角色表):
```
张华, male, 热情、歉意感强，怀旧而温暖, character sheet, front view, facing camera, neutral pose, full body, white background, concept art, anime style, high detail
```
**side.png** (侧面，img2img from front):
```
张华, male, 热情、歉意感强，怀旧而温暖, side profile view, 90 degree angle, full body, same character, same outfit, same art style, white background
```
**back.png** (背面，img2img from front):
```
张华, male, 热情、歉意感强，怀旧而温暖, back view, from behind, full body, same character, same outfit, same art style, white background
```
输出路径: characters/张华/three_view/front.png | side.png | back.png

## 二、场景三关键帧（6 张图）
每场景 3 视图：wide / closeup / mood。建议先生成 wide，再用 wide 做 img2img 生成 closeup/mood。

### 咖啡馆（scene-1）
- 时间: Day | 氛围: 温馨
- LLM 生成的 scene_prompt: A cozy urban café exterior with warm sunlight glinting off large glass windows, brass door handle and faint jingle bell visible

**wide.png** (远景建立镜头):
```
A cozy urban café exterior with warm sunlight glinting off large glass windows, brass door handle and faint jingle bell visible, wide establishing shot, full location visible, cinematic composition, no people, no characters, empty scene, concept art background, high detail, dramatic lighting
```
**closeup.png** (特写细节，img2img from wide):
```
A cozy urban café exterior with warm sunlight glinting off large glass windows, brass door handle and faint jingle bell visible, close-up detail, focus on a striking prop or texture, shallow depth of field, same art style, same palette
```
**mood.png** (氛围镜头，img2img from wide):
```
A cozy urban café exterior with warm sunlight glinting off large glass windows, brass door handle and faint jingle bell visible, atmospheric mood shot, ambient light and shadow, silhouette only, empty foreground, focus on color and tone, same art style, same palette
```
输出路径: scenes/咖啡馆/wide.png | closeup.png | mood.png

### 城市公园小径（scene-2）
- 时间: Day | 氛围: 怀旧、宁静
- LLM 生成的 scene_prompt: Autumn park path flanked by ginkgo trees, golden leaves drifting down, dappled sunlight on mossy stone path, distant lake shimmer

**wide.png** (远景建立镜头):
```
Autumn park path flanked by ginkgo trees, golden leaves drifting down, dappled sunlight on mossy stone path, distant lake shimmer, wide establishing shot, full location visible, cinematic composition, no people, no characters, empty scene, concept art background, high detail, dramatic lighting
```
**closeup.png** (特写细节，img2img from wide):
```
Autumn park path flanked by ginkgo trees, golden leaves drifting down, dappled sunlight on mossy stone path, distant lake shimmer, close-up detail, focus on a striking prop or texture, shallow depth of field, same art style, same palette
```
**mood.png** (氛围镜头，img2img from wide):
```
Autumn park path flanked by ginkgo trees, golden leaves drifting down, dappled sunlight on mossy stone path, distant lake shimmer, atmospheric mood shot, ambient light and shadow, silhouette only, empty foreground, focus on color and tone, same art style, same palette
```
输出路径: scenes/城市公园小径/wide.png | closeup.png | mood.png

## 三、角色动作视频（14 个 shot，每个 1 个视频）
每个 shot 用角色 front.png 做起始帧 + action_prompt 生成 5 秒视频。
视频生成后放到 motions/<角色名>/<action_slug>/frame_000.png ... frame_023.png（24 帧）
或直接放 mp4，我写脚本帮你转帧序列。

### shot-1（3.0秒，角色: char-1,char-2）
- action_summary: 外景过渡：咖啡馆门头特写，阳光勾勒玻璃轮廓，门铃微晃
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
The café sign 'Haven Brew' softly blurred in background, gentle breeze rustles potted herbs by the entrance
```

### shot-2（4.0秒，角色: char-1,char-2）
- action_summary: 咖啡馆内全景：阳光斜洒，木质桌椅泛暖光，吧台后咖啡师拉花，爵士乐音符可视化为柔和粒子飘浮
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Barista pours latte art; steam curls upward; vinyl record sleeve visible on shelf
```

### shot-3（5.0秒，角色: char-1）
- action_summary: 李明推门而入，肩挎帆布包，浅灰衬衫整洁，环顾四周后抬手看表，眉头微蹙，走向卡座
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
A man in light gray shirt and canvas bag enters, scanning room, checking wristwatch, walking with purpose toward window booth
```

### shot-4（4.5秒，角色: char-1）
- action_summary: 李明落座后低头轻语，手指无意识敲击桌面，目光投向门口，光影在他侧脸流动
- dialogue: 李明：（低声自语）他又迟到了……每次都是这样。
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Man leans forward slightly, lips barely moving, eyes flicking toward entrance, fingers tapping rhythmically on wood grain
```

### shot-5（3.5秒，角色: char-2）
- action_summary: 门铃轻响，张华疾步闯入，额角沁汗，呼吸微促，左手高举深蓝丝带礼盒，衣摆微扬
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
A man in navy sweater rushes in, hair slightly tousled, holding up a deep blue gift box tied with satin ribbon, smiling breathlessly
```

### shot-6（4.0秒，角色: char-1,char-2）
- action_summary: 张华快步走近，双手递出礼盒，语速急切致歉；李明略怔，伸手接过
- dialogue: 张华：对不起对不起！路上堵车——太堵了！（把盒子递过去）这个……是给你的生日礼物。
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
One man extends gift box with both hands, earnest expression; other reaches out slowly, eyes widening slightly
```

### shot-7（5.0秒，角色: char-1）
- action_summary: 李明指尖轻抚丝带，缓缓拆开，掀开盒盖——旧相册静卧绒布中，皮质封面温润，边角磨损自然
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Fingers carefully untie satin ribbon, lift lid, reveal aged leather photo album with gold-embossed title '98–02'
```

### shot-8（4.0秒，角色: char-1,char-2）
- action_summary: 两人目光交汇，嘴角同步上扬，无需言语的默契与暖意在眼神中流淌
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Both men look at each other and smile — genuine, crinkled-eye, relaxed shoulders, slight head tilt
```

### shot-9（2.0秒，角色: char-1,char-2）
- action_summary: 画面渐白，模拟老式胶片过场：轻微划痕、柔焦、暖橙色褪色滤镜
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Photo album cover dissolves into golden light, overlaid with faint film sprocket holes
```

### shot-10（4.5秒，角色: char-1,char-2）
- action_summary: 公园小径远景：金秋银杏林立，青石路蜿蜒，光斑随风摇曳，落叶轻旋
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Leaves spiral gently in breeze; light shifts across pavement like liquid gold
```

### shot-11（4.0秒，角色: char-1,char-2）
- action_summary: 中景跟拍：李明与张华并肩缓步，外套搭臂弯，步伐松弛；李明抬脚轻踢一片落叶，叶翻飞
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Two men walk side-by-side, chatting casually; one kicks leaf playfully, it flips end-over-end before settling
```

### shot-12（3.5秒，角色: char-1）
- action_summary: 李明侧脸特写，目光温柔望向前方小径，嘴角含笑，开口回忆
- dialogue: 李明：还记得我们大学时候常来这里吗？
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Man looks ahead with nostalgic smile, speaking softly, eyes slightly unfocused — remembering
```

### shot-13（5.0秒，角色: char-2）
- action_summary: 张华微微仰头，望向远处湖面，笑意沉静，右手不自觉抚过相册封皮（画外道具），声音温和悠长
- dialogue: 张华：（微笑，望向远处湖面）当然记得。那时候……我们总坐到天黑，聊理想、聊暗恋、聊怎么逃掉明天的高数课。
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Man gazes into distance, small smile playing on lips, hand resting lightly on invisible album in lap
```

### shot-14（4.5秒，角色: char-1,char-2）
- action_summary: 双人背影远景：两人沿小径渐行渐远，身影被拉长，银杏叶掠过镜头，画面淡出至暖黄余韵
- dialogue: 
- 起始帧: 用对应角色的 front.png
- **action_prompt**:
```
Two figures walk shoulder-to-shoulder down path, arms occasionally brushing, unhurried pace
```

