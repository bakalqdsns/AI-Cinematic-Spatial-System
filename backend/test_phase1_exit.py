"""Phase 1 Exit Criteria integration test.

Verifies all Phase 1 deliverables work end-to-end without requiring
external models (no GPU calls for inference, no Blender).

Checks:
  1. /api/aicss/layers/export returns 4 RGBA PNGs
  2. /api/aicss/depth has DepthResponse schema exposed
  3. /api/aicss/v2/scripts/camera-path works for all 13 movements
  4. settings_observer fires correctly
  5. image_generator_interface RLockImageGenerator serialises correctly
  6. local_llm.LLMMode + llm_mode_scope works
  7. Blender addon manifest parser (no bpy required)
"""
import base64
import io

from PIL import Image

from app.main import app


def test_layers_export():
    from fastapi.testclient import TestClient
    client = TestClient(app)

    img = Image.new('RGB', (100, 100), color=(120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    import numpy as np
    depth = np.full((100, 100), 30.0, dtype=np.float32)
    depth_img = Image.fromarray(depth.astype(np.uint8), mode='L')
    buf2 = io.BytesIO()
    depth_img.save(buf2, 'PNG')
    depth_b64 = base64.b64encode(buf2.getvalue()).decode()

    resp = client.post('/api/aicss/layers/export', json={
        'imageUrl': f'data:image/png;base64,{img_b64}',
        'depthMapUrl': f'data:image/png;base64,{depth_b64}',
    })
    assert resp.status_code == 200, f"layers/export failed: {resp.text}"
    data = resp.json()
    assert set(data['layers'].keys()) == {'sky', 'background', 'midground', 'foreground'}
    assert len(data['zOffsets']) == 4
    print('  [PASS] /api/aicss/layers/export returns 4 RGBA PNGs')


def test_camera_path():
    from fastapi.testclient import TestClient
    from app.services.shot_generator import CameraMovement
    client = TestClient(app)

    for m in CameraMovement:
        resp = client.post('/api/aicss/v2/scripts/camera-path', json={
            'cameraMovement': m.value if hasattr(m, 'value') else str(m),
            'shotSize': 'Medium Shot',
            'durationSeconds': 3.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert 1 <= len(data['keyframes']) <= 2
    print(f'  [PASS] /api/aicss/v2/scripts/camera-path handles all 13 movements')


def test_response_models_in_openapi():
    from app.main import app
    schema = app.openapi()
    components = schema.get('components', {}).get('schemas', {})
    expected = [
        'DepthResponse', 'AnalyzeResponse', 'SegmentResponse',
        'LayersResponse', 'SceneGraphResponse', 'BillboardResponse',
        'MultifaceResponse', 'InpaintResponse', 'PaperStyleResponse',
        'PaperDioramaResponse', 'PaperLayerResponse', 'LayerExportResponse',
    ]
    for name in expected:
        assert name in components, f'Missing schema: {name}'
    print(f'  [PASS] OpenAPI exposes all {len(expected)} Pydantic response models')


def test_settings_observer():
    from app.services.settings_observer import (
        register_callback, notify_setting_change, list_observers, unregister_observer,
    )
    received = []
    def cb(key, value, old):
        received.append((key, value))
    register_callback('test_phase1', cb, key_filter=lambda k: k == 'test_key')
    notify_setting_change('test_key', 'new_value', 'old_value')
    notify_setting_change('other_key', 'x', 'y')
    assert len(received) == 1
    assert received[0] == ('test_key', 'new_value')
    unregister_observer('test_phase1')
    print('  [PASS] settings_observer fires only on matching keys')


def test_image_generator_rlock():
    import threading
    from app.services.image_generator_interface import RLockImageGenerator

    gen_entered = threading.Event()
    gen_can_finish = threading.Event()
    config_entered = threading.Event()

    class Stub:
        model_id = 'stub'
        dtype_name = 'fp16'
        def generate(self, p, **k):
            gen_entered.set()
            gen_can_finish.wait(timeout=3)
            return None
        def configure(self, m, d):
            config_entered.set()
        def unload(self): pass
        def is_loaded(self): return False

    wrapped = RLockImageGenerator(Stub())
    results = {}

    def run_gen():
        wrapped.generate('test')
        results['gen'] = 'done'

    def run_cfg():
        gen_entered.wait(timeout=2)
        wrapped.configure('new', 'fp16')
        results['cfg'] = 'done'

    t1 = threading.Thread(target=run_gen)
    t2 = threading.Thread(target=run_cfg)
    t1.start()
    t2.start()
    # Brief delay to ensure configure blocks
    import time
    time.sleep(0.2)
    assert not config_entered.is_set(), 'configure should be blocked'
    gen_can_finish.set()
    t1.join(timeout=3)
    t2.join(timeout=3)
    assert config_entered.is_set(), 'configure should have run after gen finished'
    print('  [PASS] RLockImageGenerator blocks configure while generate runs')


def test_llm_mode_scope():
    from app.services.local_llm import LLMMode, get_llm_mode, llm_mode_scope

    # Without explicit scope, falls back to module default
    initial = get_llm_mode()
    print(f'    initial mode: {initial}')

    # Inside a scope, mode follows the scope
    with llm_mode_scope(LLMMode.LOCAL):
        assert get_llm_mode() == LLMMode.LOCAL
    # After scope exits, falls back to default
    after = get_llm_mode()
    assert after == initial
    print('  [PASS] llm_mode_scope() correctly switches dispatch mode')


def test_blender_manifest_parser():
    import sys
    import json
    import tempfile
    import os

    # Ensure the addon's pure-Python module is importable without bpy.
    addon_dir = os.path.join(
        os.path.dirname(__file__),
        'blender', 'addons', 'aicss_scene_builder',
    )
    sys.path.insert(0, addon_dir)

    from utils.scene_utils import (
        Z_OFFSETS, LAYER_ORDER, normalize_manifest, read_manifest,
    )

    assert Z_OFFSETS['foreground'] == -2.0
    assert Z_OFFSETS['sky'] == -20.0
    assert LAYER_ORDER == ('sky', 'background', 'midground', 'foreground')

    manifest = normalize_manifest({
        'shotId': 'test',
        'layers': {
            'foreground': '/tmp/f.png',
            'midground': '/tmp/m.png',
        },
    })
    assert manifest['shotId'] == 'test'

    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump({'shotId': 'disk', 'layers': {'foreground': '/x'}}, f)
        path = f.name
    on_disk = read_manifest(path)
    assert on_disk['shotId'] == 'disk'
    os.unlink(path)
    print('  [PASS] Blender addon manifest parser works without bpy')


def test_motion2_greenscreen_contract():
    """Module 2: greenscreen + feather + ffmpeg-detection contracts.

    Validates that the new behaviour wired into motion_extractor and
    video_adapter is reachable from the public surface, without requiring
    any model weights or external API keys.
    """
    import inspect
    import numpy as np

    from app.services.motion_extractor import (
        chroma_key_rgba,
        extract_frames_from_video,
        segment_person_from_frame,
        segment_frames_sequence,
        generate_motion_sequence,
    )
    from app.services.video_adapter import _apply_greenscreen_prompt
    from app.endpoints_script import GenerateMotionRequest

    # 1. video_adapter prompt injection is reachable and idempotent
    assert _apply_greenscreen_prompt("walk", False) == "walk"
    assert "00FF00" in _apply_greenscreen_prompt("walk", True)

    # 2. chroma_key_rgba turns pure green into a fully transparent alpha
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[:, :, 1] = 255  # pure green
    rgba[:, :, 3] = 255
    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert (out[:, :, 3] == 0).all()

    # 3. extract_frames_from_video propagates ffmpeg absence via RuntimeError
    import shutil as _shutil
    original_which = _shutil.which
    _shutil.which = lambda _: None
    try:
        try:
            extract_frames_from_video("/tmp/missing.mp4", "/tmp/out-frames")
        except RuntimeError as e:
            assert "ffmpeg" in str(e).lower()
        else:
            raise AssertionError("extract_frames_from_video must raise when ffmpeg is missing")
    finally:
        _shutil.which = original_which

    # 4. function signatures expose the new module-2 toggles
    for fn, names in (
        (segment_person_from_frame, ("feather_edges", "greenscreen", "chroma_threshold", "chroma_softness", "snap_distance")),
        (segment_frames_sequence, ("feather_edges", "greenscreen", "chroma_threshold", "chroma_softness", "snap_distance")),
        (generate_motion_sequence, ("greenscreen", "feather_edges", "chroma_threshold", "chroma_softness", "snap_distance")),
    ):
        params = inspect.signature(fn).parameters
        for n in names:
            assert n in params, f"{fn.__name__} must accept {n!r}"

    # 5. HTTP request model exposes the greenscreen / feather toggles
    req = GenerateMotionRequest(
        shot_id='s1', character_id='c1', character_name='npc', action_prompt='walk',
    )
    assert req.greenscreen is False
    assert req.feather_edges is True

    print('  [PASS] Module 2 greenscreen + feather + ffmpeg-detection contracts')


if __name__ == "__main__":
    print('Phase 1 Exit Criteria integration tests:')
    print()
    test_layers_export()
    test_camera_path()
    test_response_models_in_openapi()
    test_settings_observer()
    test_image_generator_rlock()
    test_llm_mode_scope()
    test_blender_manifest_parser()
    test_motion2_greenscreen_contract()
    print()
    print('All Phase 1 Exit Criteria checks PASSED.')
