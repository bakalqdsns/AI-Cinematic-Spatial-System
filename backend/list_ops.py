import json
d = json.load(open(r'f:\AICinematicSpatialSystem\frontend\openapi.json', encoding='utf-8'))
tags = {}
for p, methods in d['paths'].items():
    for m, op in methods.items():
        if m in ('get', 'post', 'put', 'delete', 'patch'):
            t = (op.get('tags') or ['default'])[0]
            tags.setdefault(t, []).append((m.upper(), p, op.get('operationId')))
for t in sorted(tags):
    print(f'== {t} ==')
    for m, p, opid in tags[t]:
        print(f'  {m:6} {p:65} id={opid}')
