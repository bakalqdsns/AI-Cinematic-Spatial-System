"""ComfyUI 工作流只改提示词和参考图，不改采样结构。"""
from app.services.comfyui_client import (
    MINIMAX_WORKFLOW,
    ZIMAGE_WORKFLOW,
    apply_minimax_prompt,
    apply_zimage_prompt,
    load_workflow,
    output_files,
)


def test_zimage_prompt_overrides_keep_sampler():
    graph = apply_zimage_prompt(
        load_workflow(ZIMAGE_WORKFLOW),
        "a paper tree",
        width=768,
        height=512,
        seed=7,
    )
    assert graph["67"]["inputs"]["text"] == "a paper tree"
    assert graph["68"]["inputs"]["width"] == 768
    assert graph["68"]["inputs"]["height"] == 512
    assert graph["70"]["inputs"]["seed"] == 7
    assert graph["70"]["inputs"]["steps"] == 8
    assert graph["66"]["inputs"]["unet_name"] == "z_image_turbo_bf16.safetensors"


def test_minimax_prompt_attaches_reference_image():
    graph = apply_minimax_prompt(
        load_workflow(MINIMAX_WORKFLOW),
        "walks forward",
        duration_seconds=4,
        seed=3,
        reference_filename="ref.png",
    )
    assert graph["232"]["inputs"]["value"] == "walks forward"
    assert graph["132"]["inputs"]["value"] == 4
    assert graph["235"]["inputs"]["seed"] == 3
    assert graph["9001"]["inputs"]["image"] == "ref.png"
    assert graph["136"]["inputs"]["ref_images.ref_image_0"] == ["9001", 0]
    assert graph["127"]["inputs"]["unet_name"].startswith("minimax_h3")


def test_output_files_reads_video_combine_gifs():
    entry = {"outputs": {"180": {"gifs": [{"filename": "minimax_selflift_00001.mp4", "subfolder": "", "type": "output"}]}}}
    files = output_files(entry)
    assert files[0]["filename"].endswith(".mp4")
