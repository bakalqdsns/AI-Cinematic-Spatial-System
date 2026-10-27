# 入口、配置与 HTTP 端点

本文件覆盖进程入口和全部路由模块。每个文件列出对外符号、被谁调用、以及和安全相关的具体行为。漏洞编号对应 `07-漏洞与改进方案.md`。

## `backend/run.py`

启动脚本。用 `subprocess.run` 拉起 uvicorn（约第 68、87 行）。工作目录是 backend 根。它把进程暴露面交给 `Settings.host` / `Settings.port`，本身不附加认证。

## `backend/app/__init__.py`

空包标记，无业务符号。

## `backend/app/main.py`（327 行）

| 符号 | 行 | 作用 | 依赖 |
| --- | --- | --- | --- |
| `lifespan` | 90 | 启动时 `apply_overrides`、注册 `ModelModeCascadeObserver`、`configure_dashscope_client` / `configure_llm` / `configure_image_generator`，本地模式调用 `ensure_server_running` | `settings_store`、`settings_manager.get`、`llama_server_manager` |
| `health` | 246 | 返回设备、`model_mode`、`model_manager.model_status()`、`llm_base_url`、`llm_alive` | `local_llm.get_llm_client` |
| `health_models` | 270 | 返回每个权重是否在磁盘上，异常信息截断到 500 字符后回给客户端 | `model_manager.check_models_status` |
| `root` | 307 | 指向 `/docs` 与 `/health` | 无 |

中间件在第 217–223 行：`CORSMiddleware(allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`。路由挂载：

| router 变量 | 模块 | 前缀 |
| --- | --- | --- |
| `endpoints_router` | `endpoints.py` | `/api/aicss` |
| `projects_router` | `endpoints_projects.py` | `/api/aicss` |
| `sequence_router` | `endpoints_sequence.py` | `/api/aicss` |
| `shots_router` | `endpoints_shots.py` | `/api/aicss` |
| `script_router` | `endpoints_script.py` | `/api/aicss` |
| `mesh_router` | `endpoints_mesh.py` | `/api/aicss`（router 自身还有 `/v2/meshes`） |
| `compose_router` | `endpoints_compose.py` | router 自身 `/api/aicss/v2` |
| `llm_router` | `endpoints_llm.py` | `/api/aicss/llm` |
| `settings_router` | `endpoints_settings.py` | `/api/aicss/settings` |
| `provider_router` | 同文件 | `/api/aicss/providers` |
| `models_router` | `endpoints_models.py` | 见该文件 prefix |
| `layers_router` | `endpoints_layers.py` | `/api/aicss` |
| `record_router` | `endpoints_record.py` | `/api/aicss/v2` |

没有任何 `Depends` 鉴权。`/docs` 与 `/openapi.json` 默认可访问。对应 V-01。

`health` 把 `settings.llm_base_url` 和模型状态返回给匿名调用方（V-12）。

## `backend/app/config.py`（428 行）

模块导入时就执行 `torch.cuda.is_available()`，并 `print` GPU 信息。随后写入一批进程级环境变量默认值：

| 环境变量 | 默认 | 行 |
| --- | --- | --- |
| `HF_HOME` / `HF_HUB_CACHE` / `TRANSFORMERS_CACHE` | `backend/.cache/huggingface/...` | 17–19 |
| `HF_HUB_DOWNLOAD_TIMEOUT` | `600` | 23 |
| `HF_HUB_DISABLE_XET` | `1` | 31 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 35 |
| `HF_HUB_OFFLINE` | `0` | 43 |

`Settings`（第 67 行，`env_prefix="AICSS_"`）关键字段：

| 字段 | 默认 | 被谁读取 |
| --- | --- | --- |
| `host` | `0.0.0.0` | 直接运行 `main.py` 时的绑定地址 |
| `port` | `8000` | 同上 |
| `reload` | `True` | 开发热重载；生产上会多开监视进程 |
| `workspace_dir` | `BASE_DIR / ".workspace"` | `project_store`、`video_composer`、合成下载 |
| `dashscope_*_api_key` / `toapi_llm_api_key` | `""` | `settings_manager.RUNTIME_FIELDS`、各 provider |
| `llm_base_url` / `llm_model` | 本地 OpenAI 兼容地址 | `configure_llm`、`health` |
| `providers` | 用户自定义供应商列表 | `cloud_router._get_provider_config` |

方法：

- `get_provider_config`（312）：按组件组装 `api_key`、`base_url`、模型名。注释里的示例值是占位符 `sk-xxx`，运行时读真实字段。
- `get_model_id`（384）、`list_user_providers`（388）。
- 模块级 `_check_dashscope_key`（408）：启动时检查密钥是否为空并打印组件名，不打印完整密钥。

`workspace_dir / "projects"` 在导入时 `mkdir`（第 396 行）。导入配置就会创建目录并探测 CUDA。

## `backend/app/endpoints.py`（1359 行）

前缀 `/api/aicss`。图像入口统一走 `_load_image`（431）→ `image_utils.load_image_from_url_or_base64`。请求体字段名是 `imageUrl`，类型注释写明 URL 或 base64。

| 路由函数 | 行 | 方法与路径 | 主要下游 |
| --- | --- | --- | --- |
| `analyze` | 441 | POST `/analyze` | 深度、检测、分割、图层 |
| `generate_depth` | 677 | POST `/depth` | `model_manager.depth_model` |
| `segment_objects` | 717 | POST `/segment` | GroundingDINO + SAM2 |
| `build_layers` | 805 | POST `/layers` | `spatial_utils`、图层导出 |
| `build_graph` | 852 | POST `/scene-graph` | `build_scene_graph_from_objects` |
| `generate_billboard` | 877 | POST `/billboard` | 图像裁切 |
| `generate_multiface` | 952 | POST `/multiface` | 多视角图 |
| `inpaint_image` | 1028 | POST `/inpaint` | `inpaint_utils.generate_inpaint`、LaMa |
| `occlusion_holes` | 1112 | POST `/occlusion-holes` | `occlusion_holes.compute_occlusion_holes` |
| `paper_style_transfer` | 1156 | POST `/paper-style` | `paper_diorama.paper_style_from_url` |
| `paper_diorama_generate` | 1193 | POST `/paper-diorama` | `generate_paper_diorama_textures` |
| `paper_layer_generate` | 1278 | POST `/paper-layer` | 纸模图层 |

辅助函数：`_save_project_artifact`（66）在请求带 `projectId` 时写入 `project_store`；`_sanitize_filename`（105）只处理这一路产物名。请求模型从 `ImageUrlRequest`（120）到 `PaperLayerRequest`（401），字段都是 Pydantic，没有 URL 主机白名单。对应 V-06。

这些接口会把整图放进 GPU。并发闸门 `gpu_concurrency.get_gpu_sem` 并没有包住全部路由，匿名调用可以打满显存（V-13）。

## `backend/app/endpoints_projects.py`（246 行）

| 函数 | 行 | 路径 | 路径校验 |
| --- | --- | --- | --- |
| `_validate_safe` | 59 | 内部 | 正则 `^[A-Za-z0-9_.\-]+$` |
| `create_project` | 91 | POST `/projects` | `shotId` 只 `strip`，拼进目录名 |
| `create_project_json` | 134 | POST `/projects/json` | base64 解码后同样把 `shotId` 交给 `project_store.create` |
| `list_projects` | 179 | GET `/projects` | 无 |
| `get_manifest` | 189 | GET `/projects/{project_id}/manifest` | `project_id` 未经过 `_validate_safe` |
| `get_artifact` | 199 | GET `.../artifacts/{step}/{filename}` | `step` 与 `filename` 经过 `_validate_safe` |
| `post_checkpoint` | 224 | POST `.../checkpoint` | `project_id` 未校验 |
| `delete_project` | 240 | DELETE `/projects/{project_id}` | 未校验后调用 `delete_project` |

`create` 在 `project_store.py` 第 559 行写成 `project_id = f"{ts}_{shot_id}"`，没有调用同文件的 `slugify`。`shotId` 含 `..` 或分隔符时，`mkdir(parents=True)` 会在工作区外建目录（V-03）。

`delete_project` 使用 `project_store._project_dir(project_id)`（第 242 行）。`project_id` 为 `..` 时目录是工作区的父目录，随后 `shutil.rmtree`（V-02）。

上传图片没有大小上限，`Image.open` 也没有收紧 `Image.MAX_IMAGE_PIXELS`（V-14）。

## `backend/app/endpoints_record.py`（193 行）

前缀 `/api/aicss/v2`。`_project_or_400`（25）调用 `script_record.project_dir`，该函数拒绝空串以及包含 `/`、`\`、`..` 的 `project_id`。这一组比项目删除接口严。

| 函数 | 行 | 路径 | 下游 |
| --- | --- | --- | --- |
| `get_project_record` | 33 | GET `.../projects.json` | `read_record` |
| `put_project_record` | 45 | PUT 同上 | `write_record`，body 是裸 `dict` |
| `import_project_record` | 56 | POST `/projects/import` | 从 body 取 `projectId` |
| `upload_project_file` | 69 | POST `.../files` | `write_bytes(project_id, rel, data)` |
| `get_project_file` | 86 | GET `.../file?rel=` | `resolve_rel` 后 `FileResponse` |
| `ingest_action_video` | 98 | POST `.../action-video` | `safe_token`、`extract_frames_from_video`、`segment_frames_sequence` |

`write_bytes` 允许项目目录内任意相对路径和任意字节，没有扩展名白名单，也没有大小上限。调用方可以覆盖该项目的 `projects.json`，或写入超大文件占满磁盘（V-14）。`rel` 的 `..` 被 `safe_rel` 拒绝，这一条是做得对的。

`ingest_action_video` 把异常字符串放进 JSON 的 `error` 字段（第 160 行），SAM 加载失败时会把内部异常原文返回。

## `backend/app/endpoints_settings.py`（166 行）

| 函数 | 行 | 路径 | 行为 |
| --- | --- | --- | --- |
| `get_settings` | 73 | GET `/api/aicss/settings` | `settings_manager.get_settings()`，密钥显示为 `***` |
| `post_settings` | 80 | POST 同上 | 把非空字段交给 `update_settings` |
| `get_settings_store` | 98 | GET `/store` | 返回 `settings_file_path()`，即用户主目录下的绝对路径 |
| `reset_settings_store` | 116 | DELETE `/store` | 删除并重写空的 `settings.json` |
| `get_provider_types` | 137 | GET `/api/aicss/providers/types` | `list_providers()` |
| `ping_provider` | 158 | POST `/providers/ping` | `provider_is_alive` |

`SettingsUpdate.providers` 是 `list[dict]`，其中可以带 `api_key`、`base_url`、`extra_headers`。匿名 POST 可以改 LLM 地址和云端密钥（V-05）。GET `/store` 泄露本机用户目录（V-12）。

掩码值 `***` 在 `update_settings` 里被当成普通字符串写入。前端自己避开了回写，其他客户端只要把 GET 结果再 POST 回去，就会把真密钥覆盖成三个星号（V-08）。

## `backend/app/endpoints_llm.py`（97 行）

前缀 `/api/aicss/llm`。

| 函数 | 行 | 路径 | 下游 |
| --- | --- | --- | --- |
| `llm_status` | 48 | GET `/status` | `llama_server_manager.get_status` |
| `llm_start` | 54 | POST `/start` | `start_server` |
| `llm_stop` | 68 | POST `/stop` | `stop_server` → 执行 stop 批处理 |
| `llm_reload` | 78 | POST `/reload` | 停再开 |
| `llm_keep_alive` | 91 | POST `/keep-alive` | `record_usage` |

匿名调用即可在本机拉起或关掉 `llama-server`。启动命令把服务绑到 `0.0.0.0`（见 `03` 文档）。对应 V-01、V-07。

## `backend/app/endpoints_models.py`（342 行）

| 函数 | 行 | 作用 |
| --- | --- | --- |
| `_compute_eta` | 98 | 用 `download_progress.estimate_eta` |
| `_get_model_download_info` | 110 | 组装单个模型状态 |
| `models_status` | 223 | GET 状态 |
| `download_model` | 241 | POST `/download/{model_name}`，`download_jobs.start` |

`MAX_DOWNLOAD_ATTEMPTS` 来自环境变量 `AICSS_DOWNLOAD_RETRIES`，默认 3。匿名即可触发 Hugging Face / ModelScope 下载，写 `backend/.cache`（V-13）。

## `backend/app/endpoints_script.py`（1037 行）

剧本与运动路由。请求模型从 `ParseScriptRequest`（105）到 `CameraPathResponse`（1009）。

| 函数 | 行 | 路径 | 下游 |
| --- | --- | --- | --- |
| `api_normalize_and_parse` | 286 | POST `/parse` | `script_parser.parse_script`，并 `auto_three_view.kickoff_after_parse`、`auto_scene_view.kickoff_after_parse` |
| `api_extract_characters` | 357 | POST `/characters/extract` | `extract_characters` |
| `api_generate_shots` | 390 | POST `/shots` | `shot_generator.generate_shots` |
| `api_get_scene_prompts` | 456 | POST `/scene-prompts` | 场景提示词 |
| `api_get_action_sequences` | 501 | POST `/action-sequences` | `generate_character_action_sequences` |
| `api_generate_scene_visual_prompt` | 555 | POST `/scene-visual-prompt` | `scene_generator` |
| `api_generate_visual_prompt` | 579 | POST `/visual-prompt` | `character_generator.generate_visual_prompt` |
| `api_generate_three_view` | 615 | POST `/characters/generate-three-view` | `generate_character_three_view` |
| `api_generate_variation` | 674 | POST `/characters/generate-variation` | `generate_character_variation` |
| `api_batch_status` / `api_batch_clear` | 734 / 751 | 角色批进度 | `auto_three_view.get_progress` / `clear_progress` |
| `api_generate_scene_asset` | 795 | POST `/scenes/generate-asset` | `scene_generator` |
| `api_scene_batch_status` / `clear` | 835 / 849 | 场景批进度 | `auto_scene_view` |
| `api_generate_motion` | 859 | POST `/motion/generate` | `motion_extractor.generate_motion_sequence`、`video_adapter` |
| `api_extract_frames` | 924 | POST `/motion/extract-frames` | `extract_frames_from_video` |
| `api_segment_frames` | 944 | POST `/motion/segment` | `segment_frames_sequence` |
| `api_camera_path` | 1018 | POST `/camera-path` | `camera_path_generator.build_camera_path` |

剧本正文原样进入 LLM。云模式下每次解析都会消耗外部 API 额度。匿名且无配额（V-13、V-15）。

`_strip_data_url`（90）与 `project_store._strip_data_url`、`endpoints_projects` 的 base64 解码是三套相近实现。

## `backend/app/endpoints_sequence.py`（729 行）

| 函数 | 行 | 路径 |
| --- | --- | --- |
| `analyze_sequence` | 398 | POST `/v2/sequences` |
| `analyze_from_script` | 520 | POST `/v2/sequences/from-script` |
| `get_sequence` | 549 | GET `/v2/sequences/{sequence_id}` |
| `get_scene_links` | 561 | GET `.../scene-links` |
| `get_cross_frame_object` | 638 | GET `.../objects/{global_id}` |

文件内部另有一套 `TemporalTracker`（194），方法 `_next_global_id`、`_bbox_iou`、`_class_score`、`track_frame`、`build_scene_links`、`get_cross_frame_objects`。`backend/app/utils/temporal_tracker.py` 里还有同名类。两套 IoU 与全局 ID 规则会分叉（见 `07` 的改进项 I-04）。

`_analyze_single_frame`（377）再次调用检测与 VLM。帧图来源若是 URL，走与 `endpoints.py` 相同的拉取函数（V-06）。

## `backend/app/endpoints_shots.py`（370 行）

| 函数 | 行 | 路径 | 注意 |
| --- | --- | --- | --- |
| `create_shot` | 72 | POST `/v2/projects/{project_id}/shots` | `project_id` 未白名单 |
| `list_shots` | 106 | GET 同上 | |
| `get_shot` | 139 | GET `.../{shot_id}` | |
| `delete_shot` | 165 | DELETE | `project_store.delete_shot` |
| `get_frame` | 179 | GET `.../frames/{frame_index}` | |
| `get_frame_image` | 205 | GET `.../image` | 直接回图像字节 |
| `archive_shot` | 244 | POST `.../archive` | `shot_archiver.build_shot_archive` |
| `download_shot_archive` | 284 | GET `.../archive/download` | `FileResponse` |
| `save_confirmed_layers` | 328 | POST `.../confirmed-layers` | 把 data URI 写到项目目录 |

`download_shot_archive` 第 296 行：`archives_dir.glob(f"*_{shot_id}_archive.zip")`。`shot_id` 未过滤 `*` 与路径片段。找不到精确文件时会退回 glob 的最后一项，再不行就现场 `build_shot_archive`，并把返回的 `zipPath` 交给 `FileResponse`，没有再确认该路径仍在 `archives/` 下（V-04 的相邻问题）。

文件末尾第 368 行还有一个模块级 `json_dumps`，和标准库同名，容易在后续补丁里被误用。

## `backend/app/endpoints_layers.py`（411 行）

`layers_export`（272）接收 `LayerExportRequest`（61）。辅助函数 `_decode_depth_map`（205）、`_validate_layers`（221）、`_parse_intrinsics`（242）把深度图和内参交给 `layer_exporter.export_layers` 与 `ground_reconstructor`。深度图同样可以是 URL 或 data URI。响应模型 `LayerExportResponse`（177）携带对象与地面的 data URI，体积可以很大，没有分页。

## `backend/app/endpoints_mesh.py`（488 行）

前缀 `/v2/meshes`。

| 函数 | 行 | 路径 | 下游 |
| --- | --- | --- | --- |
| `api_export_objects` | 174 | POST `/export-objects` | `mesh_exporter.export_objects_only` |
| `api_export_layers` | 249 | POST `/export-layers` | `export_layers_only` |
| `api_export_scene` | 314 | POST `/export-scene` | `export_full_scene` |
| `api_list_meshes` | 394 | GET `/list` | `project_store_mesh.list_mesh_exports` |
| `api_mesh_info` | 414 | GET `/{mesh_id}/info` | |
| `api_download_mesh` | 430 | GET `/{mesh_id}/download` | `FileResponse` |
| `api_delete_mesh` | 465 | DELETE `/{mesh_id}` | |
| `api_check_blender` | 481 | GET `/check` | `check_blender_available` |

`scene_id` 使用 `Path(project_id).name`，去掉了目录部分，比直接拼接安全。下载仍依赖 `get_mesh_file_path`，而该方法用 manifest 里的 `file_name` 拼接，没有二次 `resolve` 校验（见 `02` 文档）。

## `backend/app/endpoints_compose.py`（628 行）

文件以 UTF-8 BOM（U+FEFF）开头，`ast.parse` 会失败。运行时 Python 通常仍能导入，但格式化工具和部分静态检查会把它当成语法错误（I-06）。

| 函数 | 行 | 路径 | 行为 |
| --- | --- | --- | --- |
| `api_compose` | 101 | POST `/projects/{project_id}/compose` | `clipPaths`、`audioTracks[].path`、`colorGrade.lut_path` 原样进入 `compose_clips` |
| `get_composed_video` | 162 | GET `.../compose/{filename}` | 拒绝文件名中的分隔符和 `..`，不检查 `project_id` |
| `get_rendered_video` | 547 | GET `.../renders/{filename}` | 同上，根是 `WORKSPACE_DIR / project_id / "renders"` |
| `get_media_file` | 558 | GET `/media?path=` | `Path(path).resolve()` 后必须落在工作区或 `CACHE_DIR` |
| `refine_from_render` | 592 | POST `.../video-refine` | 按 `shot_id` glob 找 mp4，再交给视频供应商 |

`get_media_file` 用 `_is_relative_to`（571）做了根目录约束，这是全文件里最完整的一处。它仍然允许读工作区和 `.cache` 下的任意文件，包括其他项目的成片和下载缓存（V-04）。

`api_compose` 不要求片段位于该 `project_id` 目录内。ffmpeg 以列表形式接收这些路径（V-04）。`project_id` 未校验时，输出目录 `settings.workspace_dir / "projects" / pid / "compose"` 可被 `..` 带出工作区（V-02 同一类）。

`refine_from_render` 成功后 `shutil.copy2` 到 `renders/{shot_id}_refine.mp4`。`shot_id` 含分隔符时目标路径离开 `renders/`。
