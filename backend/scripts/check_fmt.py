import bpy
scene = bpy.context.scene
# 列出所有支持的 file_format
import bpy
print("===FILE_FORMATS===")
# 尝试设置各种格式
for fmt in ['FFMPEG', 'AVI_RAW', 'AVI_JPEG', 'MPEG', 'MKV', 'WEBM']:
    try:
        scene.render.image_settings.file_format = fmt
        print(f"{fmt}: OK")
    except Exception as e:
        print(f"{fmt}: FAIL - {e}")
print("===ffmpeg===")
print("has ffmpeg:", hasattr(scene.render, 'ffmpeg'))
print("ffmpeg.format type:", type(scene.render.ffmpeg.format) if hasattr(scene.render, 'ffmpeg') else "N/A")
