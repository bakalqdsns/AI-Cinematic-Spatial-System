"""Test camera-path endpoint via TestClient."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
resp = client.post('/api/aicss/v2/scripts/camera-path', json={
    'cameraMovement': 'Dolly In',
    'shotSize': 'Medium Shot',
    'durationSeconds': 4.0,
})
print('HTTP status:', resp.status_code)
data = resp.json()
print('Movement:', data['movement'])
print('ShotSize:', data['shotSize'])
print('Duration:', data['durationSeconds'])
print('Keyframes:', len(data['keyframes']))
for kf in data['keyframes']:
    pos = kf['position']
    tgt = kf['target']
    print(f'  t={kf["time"]} pos=({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}) target=({tgt[0]:.2f}, {tgt[1]:.2f}, {tgt[2]:.2f}) fov={kf["fov"]}')

# Test all 13 movements
print()
print('Testing all 13 movements:')
from app.services.shot_generator import CameraMovement
for m in CameraMovement:
    resp = client.post('/api/aicss/v2/scripts/camera-path', json={
        'cameraMovement': m.value if hasattr(m, 'value') else str(m),
        'shotSize': 'Medium Shot',
        'durationSeconds': 3.0,
    })
    assert resp.status_code == 200, f'{m} failed: {resp.status_code}'
    data = resp.json()
    assert 1 <= len(data['keyframes']) <= 2
    print(f'  {m}: {len(data["keyframes"])} kf(s) OK')
print('All 13 movements pass.')
