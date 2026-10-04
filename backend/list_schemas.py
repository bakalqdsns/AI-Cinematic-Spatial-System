import json
d = json.load(open(r'f:\AICinematicSpatialSystem\frontend\openapi.json', encoding='utf-8'))
schemas = sorted(d.get('components', {}).get('schemas', {}).keys())
print(f'total schemas: {len(schemas)}')
for s in schemas:
    print(s)
