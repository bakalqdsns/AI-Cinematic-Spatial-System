import struct, json

path = 'test_outputs/strip_stack_e2e/strip_stack_scene.glb'
data = open(path, 'rb').read()
json_chunk_len = struct.unpack_from('<I', data, 12)[0]
json_data = data[20:20+json_chunk_len].rstrip(b'\x00 ').rstrip(b' ')
j = json.loads(json_data)

print('=== All mesh primitives ===')
for mi, mesh in enumerate(j.get('meshes', [])):
    name = mesh.get('name', '?')
    print('Mesh %d: %s' % (mi, name))
    for pi, p in enumerate(mesh.get('primitives', [])):
        print('  prim[%d]: indices=%s material=%s attributes=%s' % (pi, p.get('indices'), p.get('material'), p.get('attributes')))

print()
print('=== All accessors ===')
for i, acc in enumerate(j.get('accessors', [])):
    bv_idx = acc.get('bufferView', '?')
    comp_type = acc.get('componentType', '?')
    count = acc.get('count', '?')
    typ = acc.get('type', '?')
    print('  acc[%d]: bufferView=%s componentType=%s count=%s type=%s' % (i, bv_idx, comp_type, count, typ))
