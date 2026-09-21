#!/usr/bin/env python3
"""Validate design inputs, not mechanical fitness or product readiness."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from typing import Any

def finite_positive(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v > 0

def check(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get('units') != 'mm':
        errors.append('Mechanical parameter units must be mm.')
    variants = data.get('variants')
    if not isinstance(variants, list) or not variants:
        errors.append('No envelope variants specified.')
        variants = []
    ids: set[str] = set()
    for v in variants:
        ident = v.get('id', '')
        if not ident or ident in ids:
            errors.append('Variant IDs must be non-empty and unique.')
        ids.add(ident)
        fields = ['length_mm','width_mm','thickness_mm','outline_corner_radius_mm','rim_fillet_mm']
        if not all(finite_positive(v.get(k)) for k in fields):
            errors.append(f'{ident}: missing/invalid positive dimensions.')
            continue
        if v['outline_corner_radius_mm'] >= min(v['length_mm'],v['width_mm'])/2:
            errors.append(f'{ident}: corner radius does not fit envelope.')
        if v['rim_fillet_mm'] >= min(v['thickness_mm']/2,v['outline_corner_radius_mm']):
            errors.append(f'{ident}: rim fillet too large.')
        if v.get('evidence') not in ('EST','VER','MEAS','HIST'):
            errors.append(f'{ident}: missing evidence classification.')
    unresolved = []
    paths = [('modem','exact_order_code'),('modem','exact_max_envelope_mm'),
             ('gnss','exact_order_code'),('gnss','antenna_keepout'),
             ('battery','max_pack_envelope_mm'),('battery','swelling_allowance_mm'),
             ('camera','max_module_envelope_mm'),('camera','horizontal_fov_deg'),
             ('camera','vertical_fov_deg'),('speaker','rear_cavity_volume_mm3'),
             ('seal','material')]
    for a,b in paths:
        if data.get(a,{}).get(b) is None:
            unresolved.append(f'{a}.{b}')
    if data.get('display',{}).get('decision') == 'TBD_HISTORY_CONFLICT':
        unresolved.append('display.decision')
    return {'schema_check':'PASS' if not errors else 'FAIL','errors':errors,
            'unresolved_design_inputs':unresolved,
            'assembly_fit':'NOT_RUN','waterproof':'NOT_RUN','rf':'NOT_RUN',
            'manufacturing_release':'NOT_AUTHORIZED',
            'note':'Valid parameters permit envelope study only. Missing inputs remain visible.'}

def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=Path(__file__).resolve().parents[1]/'params/core_parameters.json')
    ap.add_argument('--output', type=Path)
    ns=ap.parse_args()
    try:
        data=json.loads(ns.input.read_text(encoding='utf-8-sig'))
        report=check(data)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        report={'schema_check':'FAIL','errors':[str(exc)]}
    text=json.dumps(report,ensure_ascii=False,indent=2)
    print(text)
    if ns.output:
        ns.output.parent.mkdir(parents=True,exist_ok=True)
        ns.output.write_text(text+'\n',encoding='utf-8')
    return 0 if report['schema_check']=='PASS' else 2

if __name__ == '__main__':
    raise SystemExit(main())
