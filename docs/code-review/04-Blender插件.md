# Blender 插件 `aicss_scene_builder`

路径：`backend/blender/addons/aicss_scene_builder/`。插件在 Blender 进程内运行，权限等于启动 Blender 的用户。headless 导出由 `mesh_exporter.export_scene` 另写一份临时脚本，不经过本插件的 operator。两边的材质名、单位和图层约定必须一致，否则界面里看到的纸模和导出的 GLB 不是同一套参数。

## `__init__.py`（145 行）

`register`（87）与 `unregister`（120）登记全部 operator、面板和属性组。`bl_info` 里的版本号是 Blender 启用插件时的标识。新增 operator 只改子模块、忘记加进 `register` 的话，面板按钮会指向未注册的 `bl_idname`。

## 材质

### `materials/__init__.py`

空导出。

### `materials/paper_material.py`（305 行）

构建 Principled BSDF：漫反射、法线、厚度、透射。`mesh_exporter._generate_blender_script` 里的 `make_paper_material`（脚本模板约 487 行）复制了同一套节点，而不是 import 本文件。Blender 5.2 去掉 `Material.shadow_method` 的兼容分支在导出脚本里用 `hasattr` 做了，本文件也要保持同样的判断，否则 UI 路径在 5.2 上抛 `AttributeError`，headless 路径却能过。

节点输入名 `Subsurface Weight` 与旧版 `Subsurface` 因 Blender 版本而不同。两处都应按版本选择输入名。

## 工具与面板

### `utils/__init__.py`（22 行）

导出 `scene_utils` 的查找函数。

### `utils/scene_utils.py`（128 行）

按集合名、对象名找 AICSS 导入的平面和相机。命名约定来自 `import_layers._create_plane_for_layer` 与 `import_character_frames._create_character_plane`。改名前缀要同时改查找函数，否则灯光和渲染队列找不到对象，表现为静默跳过。

### `ui/__init__.py`

空导出。

### `ui/aicss_panel.py`（86 行）

N 面板，按钮调用下列 operator 的 `bl_idname`。面板只收集文件路径属性，真正的路径检查在 operator 的 `execute`。

## Operator

### `operators/__init__.py`

空文件。注册表在包的 `__init__.py`，不在这里。新人会在这个空文件里找导出，这是结构上的陷阱。

### `operators/import_layers.py`（297 行）

| 符号 | 行 | 作用 |
| --- | --- | --- |
| `AICSS_OT_import_layers` | 42 | 读 manifest，建图层平面 |
| `_first_frame_in_dir` | 192 | 目录里第一张图 |
| `_create_plane_for_character` | 215 | 角色卡片 |
| `_create_plane_for_layer` | 261 | 图层卡片，贴 PNG |

manifest 路径是 Blender 的 `StringProperty`。用户在本机选文件是预期行为。若后台用命令行把不可信 manifest 喂给这个 operator，JSON 里的 `png` 路径会被 `image.open`。应要求图片路径解析后仍在 manifest 所在目录内。当前 headless 主路径不走这个 operator，风险主要在有人把插件接到自动化队列时。

### `operators/import_character_frames.py`（284 行）

| 符号 | 行 | 作用 |
| --- | --- | --- |
| `_list_frames` | 36 | 帧文件列表 |
| `_load_image_sequence` | 54 | 序列图像 |
| `_apply_image_sequence_material` | 69 | 按 fps 换帧 |
| `_find_character_plane` | 117 | 用 `char_id`、`shot_id` 找对象 |
| `_create_character_plane` | 131 | 没有平面就建 |
| `AICSS_OT_import_character_frames` | 162 | 入口 |

帧目录来自记录接口写出的 `motions/<shot>_<char>/frames`。`fps` 若为 0，后面的帧号除法会抛错。应从 manifest 读取并拒绝非正数。

### `operators/layer_motion.py`（254 行）

把图层位移动画写到对象的 `location` fcurve。关键帧数值来自归档 JSON。极大位移会让 Cycles 的相机裁剪和边界盒退化，渲染时间暴涨。建议钳制到场景尺度（与 `camera_path_generator` 同一套米制单位）。

### `operators/setup_camera.py`（331 行）

| 类 | 行 | 作用 |
| --- | --- | --- |
| `AICSS_OT_setup_camera` | 34 | 静态相机、焦距、画幅 |
| `AICSS_OT_setup_camera_animation` | 142 | 把 `CameraKeyframe` 写成动画 |

关键帧字段要和 `camera_path_generator.CameraKeyframe` 以及前端 `utils/cameraAnimation.ts` 的 `CameraKeyframe` 同名。后端 DTO 在 `endpoints_script.CameraKeyframeDTO`（1001）。四套字段名目前是手工对齐的。

### `operators/add_lighting.py`（181 行）

读取 `presets/lighting/*.json`（`warm_interior.json`、`misty_grey.json`、`tense_night.json` 等）。预设名应只允许文件名，不允许路径。JSON 里的能量值直接进灯光，没有上限。`shot_archiver._load_lighting_preset` 读的是同一批文件。前端 `lighting/presets.ts` 还有一份给 Three.js 的预设。三份灯光数值会不一致，画面和最终渲染对不上（I-07）。

### `operators/apply_material.py`（106 行）

对选中对象调用 `paper_material`。对象不在 AICSS 集合里时仍然会换材质，可能改掉用户自己的物体。`execute` 应限制集合。

### `operators/verify_cycles.py`（150 行）

`AICSS_OT_verify_cycles`（28）检查渲染引擎能否切到 Cycles、GPU 设备是否可用。失败信息通过 `self.report` 给用户，不回传到 FastAPI。后端 `check_blender_available` 只检查可执行文件能不能启动，不检查 Cycles GPU。前端看到“Blender 可用”仍可能在渲染时掉到 CPU。

### `operators/render_queue.py`（399 行）

| 符号 | 行 | 作用 |
| --- | --- | --- |
| `_split_paths` | 40 | 把文本拆成路径列表 |
| `_clear_scene` | 52 | 清空当前场景 |
| `_configure_cycles` | 70 | 采样数与 device |
| `_configure_ffmpeg` | 93 | 输出编码 |
| `_render_one_shot` | 107 | 单个 manifest |
| `AICSS_OT_render_queue` | 258 | 批量 |

`_clear_scene` 会删掉打开的文件里的对象。自动化调用前必须使用独立 `.blend` 或 `--background` 空场景。`endpoints_compose` 的渲染队列如果复用用户正在编辑的文件，会清掉该文件。

`_split_paths` 按分隔符切路径，不拒绝绝对路径。队列文件里写什么就渲染什么，输出目录也来自参数。这是本机设计师工具的预期能力；一旦队列文件来自未校验的 HTTP 字段，就和 `compose_clips` 的任意路径同级。后端触发渲染时要先把 manifest 复制到项目目录，再只把那个绝对路径传给 Blender。

采样数没有硬顶。匿名或误操作把 samples 设到几千，会长时间占 GPU。

## 插件与后端的对应关系

| 插件符号 | 后端 / 前端对应 |
| --- | --- |
| `paper_material` 节点 | `mesh_exporter` 模板函数 `make_paper_material` |
| `import_layers` 的 PNG 路径 | `layer_exporter.export_layers_to_disk`、`project_store.save_step` |
| `import_character_frames` 的帧目录 | `motion_extractor.extract_frames_from_video`、`script_record.write_bytes` |
| `setup_camera_animation` | `camera_path_generator.build_camera_path`、`CameraKeyframeDTO` |
| `add_lighting` 预设名 | `shot_archiver._load_lighting_preset`、`lighting/presets.ts` |
| `render_queue` 输出 mp4 | `get_rendered_video` 读 `renders/{filename}` |
| `verify_cycles` | `mesh_exporter.check_blender_available` 只检查二进制，不检查 Cycles |

插件代码里没有网络请求，也没有 `eval`。风险集中在“路径和清空场景”这两类操作被自动化调用时缺少与 HTTP 层相同的沙箱。
