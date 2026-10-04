"""
Test DashScope client directly
"""
import os
import sys

# Add backend to path
sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend")

# Set API key
os.environ["AICSS_DASHSCOPE_LLM_API_KEY"] = "sk-be08ad3df19b4114affd9b03168816c7"
os.environ["AICSS_DASHSCOPE_IMAGE_API_KEY"] = "sk-be08ad3df19b4114affd9b03168816c7"

from app.services.dashscope_client import get_dashscope_client, DEFAULT_LLM_MODEL, DEFAULT_IMAGE_MODEL

print(f"DEFAULT_LLM_MODEL: {DEFAULT_LLM_MODEL}")
print(f"DEFAULT_IMAGE_MODEL: {DEFAULT_IMAGE_MODEL}")

client = get_dashscope_client()
print(f"Client LLM model: {client.llm_model}")
print(f"Client Image model: {client.image_model}")

print("\n" + "=" * 60)
print("Test LLM chat")
print("=" * 60)

try:
    result = client.chat([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one word."}
    ])
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("Test Image generation")
print("=" * 60)

try:
    urls = client.generate_image("A beautiful mountain landscape at sunset")
    print(f"Generated {len(urls)} images")
    if urls:
        print(f"First URL: {urls[0][:100]}...")
except Exception as e:
    print(f"Error: {e}")
