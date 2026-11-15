"""Minimal dependency-free PDF renderer for concise field case reports."""
from __future__ import annotations
import json
import re


def _ascii(text: str) -> str:
    text = text.encode("cp1252", errors="replace").decode("cp1252")
    return "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in text)


def _pdf_literal(text: str) -> str:
    return _ascii(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_field_report(corridor: str, granule: str, result: dict, provenance: dict) -> bytes:
    lines = ["STRAINLINE | FIELD EVIDENCE CASES", f"Corridor: {corridor}", f"Granule: {granule}",
             f"Three-Lane status: {result.get('status', 'unavailable')}",
             "SCREENING INVESTIGATION ONLY - NOT A DAMAGE OR SAFETY ASSESSMENT", ""]
    for case in result.get("cases", []):
        lines += [f"CASE {case.get('case_id')} | {case.get('status')}",
                  f"Chainage: {float(case.get('chainage_m',0))/1000:.3f} km",
                  f"Location: {case.get('latitude', 'unavailable')} latitude, {case.get('longitude', 'unavailable')} longitude",
                  f"Railway LOS: {case.get('asset_los_mm')} mm",
                  f"Control A LOS: {case.get('control_a_los_mm')} mm",
                  f"Control B LOS: {case.get('control_b_los_mm')} mm",
                  f"Asset-relative: {case.get('asset_relative_mm')} mm",
                  f"Reason: {', '.join(case.get('reason', [])) or 'candidate difference'}",
                  f"Terrain/radar matching record: {json.dumps(case.get('terrain_match_metrics', {}), sort_keys=True)}",
                  f"Documented context: {json.dumps(case.get('context', []), ensure_ascii=True)}",
                  "Observation history:"]
        history = case.get("temporal_history") or {}
        if history.get("observations"):
            lines += [f"History status: {history.get('status', 'available')} | usable observations: {history.get('valid_observations', 0)}",
                      f"Absolute asset net change: {history.get('asset_absolute_net_change_mm')} mm",
                      f"Asset-relative net change: {history.get('asset_relative_net_change_mm')} mm",
                      f"Asset-relative range: {history.get('asset_relative_range_mm')} mm"]
            for observation in history["observations"]:
                lines.append(f"{observation.get('date')} | {observation.get('granule_id')} | asset {observation.get('asset_los_mm')} mm | background {observation.get('background_los_mm')} mm | relative {observation.get('asset_relative_mm')} mm")
        else:
            lines.append(f"Unavailable: {history.get('reason', 'No compatible multi-observation history was supplied for this chainage.')}")
        for missing in history.get("missing_observations", []):
            lines.append(f"No-call {missing.get('date')} | {missing.get('granule_id')} | {missing.get('reason')}")
        robustness = case.get("reference_robustness") or {}
        lines += [f"Reference robustness: {robustness.get('classification', 'not evaluated')} | median portfolio spread {robustness.get('median_signal_spread_mm')} mm"]
        for scenario in robustness.get("scenarios", []):
            value = scenario.get("asset_relative_mm")
            lines.append(f"{scenario.get('configuration')}: {scenario.get('status')}" + (f" | {value} mm" if value is not None else ""))
        if robustness.get("method"):
            lines.append(f"Robustness method: {robustness['method']}")
        plan = case.get("verification_plan", [])
        lines.append("Proposed field verification stops:")
        if plan:
            for stop in plan:
                lines.append(f"{stop.get('location', 'Stop')}: {stop.get('measure', 'measurement unspecified')} | latitude {stop.get('latitude', 'unavailable')} | longitude {stop.get('longitude', 'unavailable')} | chainage {stop.get('chainage_m', 'unavailable')} m")
        else:
            lines.append("No location-specific field stops were supplied for this case.")
        lines += ["Proposed measurements only; no defect diagnosis or repair recommendation.", ""]
    lines += ["PROVENANCE", json.dumps(provenance, sort_keys=True, ensure_ascii=True)]
    wrapped=[]
    for line in lines:
        text=_ascii(line)
        while len(text)>95:
            cut=text.rfind(" ",0,95)
            if cut<20:cut=95
            wrapped.append(text[:cut]);text=text[cut:].lstrip()
        wrapped.append(text)
    pages=[wrapped[i:i+48] for i in range(0,len(wrapped),48)] or [[]]
    objects=[]
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    kid_ids=[4+i*2 for i in range(len(pages))]
    objects.append(f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in kid_ids)}] /Count {len(pages)} >>")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for index, page_lines in enumerate(pages):
        page_id=4+index*2; content_id=page_id+1
        stream_parts=["BT", "/F1 10 Tf", "52 744 Td", "14 TL"]
        for line in page_lines:
            if line.startswith("CASE "): stream_parts.append("/F1 12 Tf")
            elif line in ("STRAINLINE | FIELD EVIDENCE CASES", "PROVENANCE"): stream_parts.append("/F1 14 Tf")
            stream_parts.append(f"({_pdf_literal(line)}) Tj T*")
            if line.startswith("CASE ") or line == "PROVENANCE": stream_parts.append("/F1 10 Tf")
        stream_parts.append("ET")
        stream="\n".join(stream_parts).encode("ascii")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n"+stream.decode("ascii")+"\nendstream")
    pdf=bytearray(b"%PDF-1.4\n%StrainLine\n"); offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(pdf));pdf.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode("ascii"))
    xref=len(pdf);pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)
