"""
Test config loading
"""
import os
import sys

# Add backend to path
sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend")

from app.config import settings

print(f"DashScope LLM API Key: {settings.dashscope_llm_api_key[:10] if settings.dashscope_llm_api_key else 'NOT SET'}...")
print(f"DashScope Image API Key: {settings.dashscope_image_api_key[:10] if settings.dashscope_image_api_key else 'NOT SET'}...")
print(f"Model mode: {settings.model_mode}")
