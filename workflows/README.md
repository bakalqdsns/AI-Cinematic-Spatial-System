# ComfyUI 工作流使用说明

5 个可直接拖拽的 ComfyUI 工作流 JSON 文件，位于 `f:\AICinematicSpatialSystem\workflows\`。

---

## 快速上手（3 步）

### 1. 启动 ComfyUI

```bash
# 在 WSL Ubuntu 内
cd ~/projects/aicss-tools/comfyui
source venv/bin/activate
python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch
```

### 2. 浏览器打开 ComfyUI

Windows 浏览器访问 `http://127.0.0.1:8188`（WSL2 自动转发）。

### 3. 导入工作流

在 ComfyUI 界面：

1. 按 **Ctrl + O**（或菜单 `Workflow` → `Open`）
2. 选择 `F:\AICinematicSpatialSystem\workflows\*.json`
3. **直接显示在工作区**，无需重启

---

## 5 个工作流速览

| 文件名 | 用途 | 模型 | 节点数 | 显存 | 耗时 |
|--------|------|------|--------|------|------|
| `txt2img_basic.json` | 基础文生图（概念图/灵感图） | Z-Image-Turbo fp8 | 9 | ~5GB | ~8s |
| `character_three_view.json` | 角色 front/side/back 三视图 | Z-Image-Turbo fp8 | 18 | ~5GB | ~20s |
| `depth_anything_v2.json` | RGB → 深度图（2.5D 视差） | Depth-Anything-V2-Large | 8 | ~3GB | ~4s |
| `lama_inpaint.json` | 物体移除/水印擦除/区域修复 | LaMa + 可选 DINO+SAM2 | 12 | ~4GB | ~6s |
| `wan2.1_i2v.json` | 单帧 → 5秒480p 视频 | Wan2.1-I2V (14B 或 1.3B) | 14 | ~14GB | ~3min |

---

## 每个工作流的关键参数

### 1. `txt2img_basic.json`

**修改 PROMPT 节点 → 节点 2**（CLIPTextEncode，标题 "POSITIVE PROMPT"）

```
把整段文本替换成你的画面描述，例如：
aesthetic concept art, full body character, 
centered composition, paper craft style, ...
```

**关键 KSampler 参数**：

```
steps: 20        # Z-Image-Turbo 蒸馏模型固定 20 步
cfg: 1.0         # 蒸馏模型 cfg=1，不要改
sampler: euler_ancestral
denoise: 1.0     # 全噪声 → 完整生成
```

**节点 7 (VAE Loader)**：如果你没有 `sdxl_vae.safetensors`，**直接删除它**，把节点 1 的 VAE 输出（pin 2）连到节点 6 的 VAE 输入即可。

---

### 2. `character_three_view.json`

**三个 PROMPT 节点对应三个视角**：

| 节点 | 标题 | 内容 |
|------|------|------|
| 2 | FRONT VIEW PROMPT | `character turnaround front view, face directly facing camera, ...` |
| 3 | SIDE VIEW PROMPT | `character turnaround side view, profile view from left, ...` |
| 4 | BACK VIEW PROMPT | `character turnaround back view, character facing away from camera, ...` |

**修改角色特征**：三个节点的 prompt 里都有这一段，统一替换即可：

```
17-year-old Chinese high school girl, 
long straight black hair, brown eyes, 
school uniform with white shirt and blue ribbon, 
gentle but melancholic expression
```

**节点 18 (ImageGrid)**：自动把三视图拼成一张，方便对比。

---

### 3. `depth_anything_v2.json`

**节点 1 (LoadImage)**：上传你的图像 → 填文件名 → 运行。

**输出**：
- 节点 6（SaveImage）：灰度深度图（给 AI pipeline 用）
- 节点 7（SaveImage）：彩色可视化深度图（人眼看）

---

### 4. `lama_inpaint.json`

**两种用法**：

#### 方式 A：手动 mask

1. 节点 1（LoadImage）→ 上传原图
2. 节点 2（LoadImage）→ 上传 mask（白色 = 待修复区域，黑色 = 保留）
3. 运行

#### 方式 B：自动 mask（语义分割）

1. 节点 1（LoadImage）→ 上传原图
2. 节点 10（GroundingDinoSAM2Segment）→ 在 prompt widget 里写想移除的东西，例如：
   ```
   person . chair . bag . umbrella
   ```
   （用 `.` 分隔多个类别）
3. 运行 → 自动生成 mask → 节点 11/12 → 节点 4 (LaMa) 修复

---

### 5. `wan2.1_i2v.json`

**节点 2 (LoadImage)**：上传关键帧（建议 720×480 横版）。

**节点 1 (WanVideoLoader)**：根据显存选择模型：

| 模型 | 显存 | 推荐 |
|------|------|------|
| `wan2.1_i2v_14b_fp8.safetensors` | ~14GB | RTX 4070+ 16GB 显卡 |
| `wan2.1_i2v_1.3b_480p.safetensors` | ~3GB | 所有显卡（画质较低） |

**输出位置**：`ComfyUI/output/aicss_video_5s_xxxxx.mp4`

**参数说明**：

```
num_frames: 81   # 5秒 @ 16fps
fps: 16          # 标准电影帧率
steps: 30        # 推荐 30 步
cfg: 4.0         # Wan2.1 推荐 4.0
sampler: uni_pc  # Wan2.1 专用 sampler
```

---

## 通用技巧

### 解决模型未找到

工作流加载后如果节点报红（找不到模型）：

```
1. 打开节点，看 ckpt_name / model_name 输入框
2. 输入框可下拉选择你本地已有的模型文件名
3. 或者下载对应模型到 models/ 对应子目录
```

### 解决自定义节点缺失

如果显示某个节点未安装（例如 `DepthAnythingV2Advanced`）：

```bash
cd ~/projects/aicss-tools/comfyui/custom_nodes

# 安装 Depth Anything V2 节点
git clone https://github.com/kijai/ComfyUI-DepthAnythingV2.git

# 安装 LaMa 修复节点
git clone https://github.com/luxuus/ComfyUI-Inpaint-Utils.git

# 安装 GroundingDINO+SAM2 节点
git clone https://github.com/spacepxl/ComfyUI-GroundingDINO-SAM2.git

# 安装 Wan2.1 节点
git clone https://github.com/city96/ComfyUI-WanVideoWrapper.git

# 重启 ComfyUI（自动检测新节点）
```

### 解决断线（link 缺失）

如果导入后部分节点之间连线断了：
- 一般是因为节点编号冲突（你当前界面已有同名节点）
- 解决：先 `Ctrl + A` 全选 → Delete 清空画布，再 `Ctrl + O` 打开 JSON

---

## 故障排查

### Q: 工作流加载后一片空白 / 部分节点不可见

**A**: 节点位置在画布外。按 `Home` 键或 `View` → `Reset View` 缩放定位。

### Q: 提交后报 "Prompt execution failed"

**A**: 节点报错会把出错的节点红框显示。鼠标悬停查看具体错误。常见：
- 模型文件不存在 → 检查 `models/` 目录
- 显存不足 → 关掉其他 GPU 进程 / 用更小模型
- 插件版本不匹配 → 更新 custom_nodes

### Q: Wan2.1 视频生成很慢 / OOM

**A**: 改用 1.3B 模型 + 480p + num_frames=49（约 3 秒）。4060 Ti 16GB 跑 14B fp8 在 480p 下勉强能跑，但建议用 1.3B 主力。

### Q: 想换不同 checkpoint 但提示词不变

**A**: 节点 1 (CheckpointLoaderSimple) 的 `ckpt_name` widget 是下拉选择，所有依赖该模型的下游节点会自动跟随。

---

## 工作流与 Dify 的集成

这些工作流 JSON 可以直接被 Dify 工作流的 `Code` 节点读取并修改：

```python
# Dify Code 节点里
import json, uuid
template = json.load(open("/app/workflow_export/character_three_view.json"))
# 动态修改 prompt
template["2"]["inputs"]["text"] = f"character turnaround front view, {user_input}, paper craft style"
# 动态修改 seed
template["9"]["inputs"]["seed"] = abs(hash(user_input)) % (10**8)
# 提交
requests.post("http://host.docker.internal:8188/prompt", json={"prompt": template, "client_id": str(uuid.uuid4())})
```

更详细集成方式参考：`docs/thesis/ComfyUI_Dify手动搭建实战手册.md`

---

## 一键验证脚本

```bash
# 把所有工作流快速导入到 ComfyUI 看是否能解析
# （ComfyUI 启动后 API 可用）
for f in F:\AICinematicSpatialSystem\workflows\*.json; do
    echo "==> Validating: $(basename $f)"
    python -c "
import json
with open('$f') as fp:
    w = json.load(fp)
nodes = {n['id']: n for n in w['nodes']}
links = w.get('links', [])
print(f'  Nodes: {len(nodes)}, Links: {len(links)}')
for n in w['nodes']:
    if n['type'] in {'CheckpointLoaderSimple', 'LoadImage', 'SaveImage'}:
        print(f'  {n[\"id\"]}: {n[\"type\"]} = {n.get(\"widgets_values\", [\"?\"])[0]}')"
done
```

---

*文档生成时间: 2026-08-01*
*所有工作流基于 ComfyUI v0.3+ API 格式（version=0.4）*