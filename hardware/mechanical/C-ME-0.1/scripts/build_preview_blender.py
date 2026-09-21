"""Import the supplied mm-STL as meters, verify dimensions, save a NEW .blend.
Usage: blender --background --python build_preview_blender.py -- --root ROOT
Does not render images, install add-ons, access hardware, or change original STL.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys
import bpy

argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
ns=ap.parse_args(argv)
root=ns.root.resolve()
params=json.loads((root/'params/core_parameters.json').read_text(encoding='utf-8-sig'))
# New background process is expected. Do not reset a user's active GUI scene.
if not bpy.app.background:
    raise RuntimeError('Use --background in a separate Blender process; existing GUI scene is not modified.')
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj,do_unlink=True)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.scale_length=1.0
scene.unit_settings.length_unit='MILLIMETERS'
rows=[]
for i,v in enumerate(params['variants']):
    p=root/'cad'/(v['id']+'_ENVELOPE_ONLY.stl')
    if not p.is_file():
        raise FileNotFoundError(str(p))
    before=set(bpy.data.objects)
    if hasattr(bpy.ops.wm,'stl_import'):
        bpy.ops.wm.stl_import(filepath=str(p),global_scale=1.0,use_scene_unit=False)
    else:
        raise RuntimeError('This script expects the built-in wm.stl_import operator. Use your version help/manual and adapt; do not auto-install add-ons.')
    new=[x for x in bpy.data.objects if x not in before and x.type=='MESH']
    if len(new)!=1:
        raise RuntimeError('One envelope mesh per STL expected.')
    obj=new[0]
    # Input coordinates have numeric millimeters; Blender data now stores meters.
    for vertex in obj.data.vertices:
        vertex.co *= 0.001
    obj.data.update()
    bpy.context.view_layer.update()
    xyz=[float(k)*1000.0 for k in obj.dimensions]
    expected=[v['width_mm'],v['length_mm'],v['thickness_mm']]
    if any(abs(a-b)>0.05 for a,b in zip(xyz,expected)):
        raise RuntimeError('Unit or axis mismatch: '+v['id']+' '+str(xyz))
    obj.name=v['id']+'_ENVELOPE_ONLY_EST'
    obj['status']='NO_INTERNAL_ASSEMBLY; NO_IP_CLAIM'
    obj['mechanical_units']='mm in source; meter coordinates in Blender'
    obj['source_revision']=params['design_revision']
    # Spacing belongs to the presentation scene only; never export it as assembly placement.
    obj.location.x=i*0.085
    rows.append({'id':v['id'],'xyz_mm':xyz,'unit_check':'PASS','assembly_fit':'NOT_RUN'})
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
out=root/'cad'/('blender_local_'+stamp)
out.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'EGOLINK_ENVELOPE_COMPARISON.blend'))
(out/'BLENDER_RUN_REPORT.json').write_text(json.dumps({'version':bpy.app.version_string,'outputs':rows,'source_revision':params['design_revision']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Saved envelope comparison to',out)
