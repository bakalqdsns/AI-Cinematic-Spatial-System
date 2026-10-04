"""
Direct test of DashScope APIs with correct API
"""
import os
import sys

# Set the API key directly
api_key = "sk-be08ad3df19b4114affd9b03168816c7"
os.environ["DASHSCOPE_API_KEY"] = api_key

print("=" * 60)
print("Test 1: DashScope ImageGeneration (wan2.6-t2i)")
print("=" * 60)

try:
    from dashscope import ImageGeneration

    response = ImageGeneration.call(
        model="wan2.6-t2i",
        messages=[
            {"role": "user", "content": "A beautiful ancient forest, mystical atmosphere, cinematic lighting, concept art style"}
        ],
        api_key=api_key,
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response}")

    if response.status_code == 200:
        images = response.output.images
        print(f"Generated images: {len(images)}")
        for img in images:
            print(f"  URL: {img.url}")
    else:
        print(f"Error: {response.message}")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test 2: DashScope ImageSynthesis (wanx-v1)")
print("=" * 60)

try:
    from dashscope import ImageSynthesis

    response = ImageSynthesis.call(
        model="wanx-v1",
        prompt="A beautiful ancient forest, mystical atmosphere, cinematic lighting, concept art style",
        size="1024*1024",
        n=1,
        api_key=api_key,
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response}")

    if response.status_code == 200:
        images = response.output.images
        print(f"Generated images: {len(images)}")
        for img in images:
            print(f"  URL: {img.url}")
    else:
        print(f"Error: {response.message}")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test 3: DashScope Generation (qwen-plus)")
print("=" * 60)

try:
    from dashscope import Generation

    response = Generation.call(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in one sentence."}
        ],
        temperature=0.7,
        api_key=api_key,
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response}")

    if response.status_code == 200:
        print(f"Output: {response.output.choices[0].message.content}")
    else:
        print(f"Error: {response.message}")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Done")
print("=" * 60)
