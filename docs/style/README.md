# 全系统场景风格基准：手工纸雕 HD-2D（《纸间行》）

`paper-diorama-reference.jpg` 是全系统**所有场景出图**的统一风格基准图。

## 风格特征（取自基准图）

- 手工纸雕立体模型（handcrafted paper diorama）
- 层叠剪纸艺术（layered paper cutout art）
- 卡纸纹理（construction paper texture）
- 纸做的教学楼 / 树 / 跑道 / 远山（paper-crafted buildings, trees and distant mountains）
- 移轴微缩模型摄影感（tilt-shift miniature scale model photography）
- 暖金色斜阳（warm golden low-angle sunlight）
- 近实远虚的景深（strong depth of field, sharp near layers with softly blurred distant layers）

## 代码对应

这些特征是 `backend/app/services/scene_style.py` 中 `SCENE_STYLE_SUFFIX` 的
措辞来源（原始措辞来自 `F:\zimage-lora\gen_zhijing_scenes.py` 的 `STYLE`，
按基准图微调）。负面词为同一模块的 `SCENE_NEGATIVE_PROMPT`。

- 场景出图（wide / closeup / mood），无论走 comfyui、diffusers、zimage_lora
  还是云端通路，都必须经过 `scene_style.apply_scene_style`（幂等）。
- 人物出图的人物本体使用同一纸雕风格（`CHARACTER_STYLE_SUFFIX` /
  `apply_character_style`），但**背景永远只是绿幕**：绿幕条款
  （`_FLAT_CYCLORAMA_CLAUSE` 和固定 `#00FF00` 后缀）一字不动、保持最后，
  风格词只加在人物描述部分。

修改风格措辞时：只改 `scene_style.py`，并同步更新本文件与基准图说明。
