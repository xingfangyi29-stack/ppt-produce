from typing import Any, Dict, List, Optional, Tuple
import re

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
NUMBER_RE = re.compile(r"(-?\d{1,3}(?:[\.,]\d+)?)")


def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace('%', '')
    try:
        return float(s.replace(',', '.'))
    except Exception:
        m = NUMBER_RE.search(s)
        if m:
            try:
                return float(m.group(1).replace(',', '.'))
            except Exception:
                return None
    return None


def _map_table_years(table: List[List[str]], global_years: Optional[List[int]] = None) -> Optional[List[int]]:
    # Try first two rows for year labels
    for row in table[:2]:
        years = []
        for cell in row:
            if not cell:
                continue
            m = YEAR_RE.search(cell)
            if m:
                try:
                    years.append(int(m.group(0)))
                except Exception:
                    pass
        if years:
            return years
    return global_years


def _extract_series_from_table(table: List[List[str]]) -> Dict[str, List[Optional[float]]]:
    series = {}
    for row in table:
        if not row:
            continue
        label = row[0].strip() if row[0] else None
        if not label:
            continue
        vals: List[Optional[float]] = []
        for cell in row[1:]:
            val = _to_float(cell)
            vals.append(val)
        series[label] = vals
    return series


def _find_tables_in_slides(slides: List[Dict[str, Any]]) -> List[Tuple[int, List[List[str]]]]:
    tables = []
    for s in slides:
        if s.get('tables'):
            for t in s['tables']:
                tables.append((s.get('slide_number'), t))
    return tables


def _score_candidate(last: Optional[float], change: Optional[float], benchmark_gap: Optional[float], monotonic_decline: bool, has_driver: bool) -> int:
    score = 0
    if last is not None and last < 60:
        score += 40
    if change is not None and change <= -5:
        score += 30
    if benchmark_gap is not None and benchmark_gap <= -3:
        score += 20
    if monotonic_decline:
        score += 25
    if has_driver:
        score += 5
    return score


def _choose_top(cands: List[Dict[str, Any]], limit: int = 2) -> List[Dict[str, Any]]:
    sorted_c = sorted(cands, key=lambda x: (-x['score'], x.get('label', '')))
    return sorted_c[:limit]


def generate_discussion_areas(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate exactly 2 discussion directions based on parsed survey data.

    Each discussion area contains:
      - title
      - why_discuss
      - discussion_prompt
      - supporting_data

    The generator is rule-based and must NOT invent numeric data. All numeric claims
    are taken from parsed.
    """
    slides = parsed.get('slides') or []
    years = parsed.get('years') or []
    overall = parsed.get('overall_score')
    benchmark = parsed.get('benchmark')
    participation = parsed.get('participation_rate')
    dimensions_global = parsed.get('dimensions') or []
    drivers_global = parsed.get('drivers') or []

    candidates: List[Dict[str, Any]] = []

    # 1) Participation candidate (if present)
    if participation is not None:
        score = 0
        if participation < 50:
            score += 60
        elif participation < 60:
            score += 20
        # check for participation trend in slides (found_participation fields)
        part_vals = []
        for s in slides:
            if s.get('found_participation') is not None:
                # if slide has years, map it; we'll just collect values
                part_vals.append(s.get('found_participation'))
        change = None
        if len(part_vals) >= 2:
            change = part_vals[-1] - part_vals[-2]
            if change <= -10:
                score += 30
        if score > 0:
            supporting = f"Participation rate: {participation:.1f}%"
            if change is not None:
                supporting += f"; Trend change (last two): {change:+.1f} pts"
            candidates.append({
                'label': 'Participation rate',
                'score': score,
                'last': participation,
                'change': change,
                'benchmark_gap': None,
                'has_driver': False,
                'source_fields': ['participation_rate'],
                'supporting_data': supporting,
                'reason_tags': ['participation']
            })

    # 2) Benchmark gap overall
    if overall is not None and benchmark is not None:
        gap = overall - benchmark
        if gap < -3:
            score = 50
            candidates.append({
                'label': 'Overall engagement benchmark gap',
                'score': score,
                'last': overall,
                'change': None,
                'benchmark_gap': gap,
                'has_driver': False,
                'source_fields': ['overall_score', 'benchmark'],
                'supporting_data': f"Overall: {overall:.1f}; Benchmark: {benchmark:.1f}; Gap: {gap:.1f}",
                'reason_tags': ['benchmark_gap']
            })

    # 3) Dimension-level candidates from tables and slides
    tables = _find_tables_in_slides(slides)
    for slide_num, table in tables:
        header_years = _map_table_years(table, years)
        series = _extract_series_from_table(table)
        for label, vals in series.items():
            # skip rows that look like overall
            if 'overall' in label.lower():
                continue
            if all(v is None for v in vals):
                continue
            # last non-null value
            last_val = None
            non_null_vals = [v for v in vals if v is not None]
            if non_null_vals:
                last_val = non_null_vals[-1]
            # compute simple change between last two non-null
            change = None
            if len(non_null_vals) >= 2:
                change = non_null_vals[-1] - non_null_vals[-2]
            # monotonic decline/increase check (len >=3)
            monotonic_decline = False
            if len(non_null_vals) >= 3:
                dec = all(x > y for x, y in zip(non_null_vals, non_null_vals[1:]))
                inc = all(x < y for x, y in zip(non_null_vals, non_null_vals[1:]))
                if dec:
                    monotonic_decline = True
            # benchmark gap if benchmark exists
            bench_gap = None
            if last_val is not None and benchmark is not None:
                bench_gap = last_val - benchmark
            has_driver = False
            # check if this label appears in drivers_global or slides driver_candidates
            if any(d and label.lower() in d.lower() for d in (drivers_global or [])):
                has_driver = True
            for s in slides:
                if s.get('driver_candidates'):
                    if any(label.lower() in (dc.lower() if dc else '') for dc in s.get('driver_candidates')):
                        has_driver = True
            # score
            cand_score = _score_candidate(last_val, change, bench_gap, monotonic_decline, has_driver)
            if cand_score <= 0:
                continue
            support_parts = []
            if last_val is not None:
                support_parts.append(f"Latest: {last_val:.1f}")
            if change is not None:
                support_parts.append(f"Change(last two): {change:+.1f}")
            if bench_gap is not None:
                support_parts.append(f"Gap vs benchmark: {bench_gap:+.1f}")
            supporting = '; '.join(support_parts) if support_parts else None
            candidates.append({
                'label': label,
                'score': cand_score,
                'last': last_val,
                'change': change,
                'benchmark_gap': bench_gap,
                'has_driver': has_driver,
                'source_fields': [f'slide_{slide_num}_table_row_{label}', 'benchmark' if bench_gap is not None else None],
                'supporting_data': supporting,
                'reason_tags': ['dimension']
            })

    # 4) Dimensions or topics found as candidates in slide dimension_candidates or driver_candidates
    # promote short-listed global dimensions if present and not already in candidates
    existing_labels = {c['label'].lower() for c in candidates}
    for sd in slides:
        for dc in (sd.get('dimension_candidates') or []):
            if not dc:
                continue
            if dc.lower() in existing_labels:
                continue
            # heuristics: no numeric series but a candidate dimension appears - lower priority
            candidates.append({
                'label': dc,
                'score': 10,
                'last': None,
                'change': None,
                'benchmark_gap': None,
                'has_driver': False,
                'source_fields': [f"slide_{sd.get('slide_number')}_dimension_candidate"],
                'supporting_data': None,
                'reason_tags': ['dimension_candidate']
            })

    # Sort and pick top 2
    chosen = _choose_top(candidates, limit=2)

    # If fewer than 2 chosen, create data-insufficiency placeholders linked to missing fields
    discussion_areas: List[Dict[str, Any]] = []
    for c in chosen:
        label = c.get('label')
        # Create title
        title = f"Discuss: {label}"
        # Build why_discuss using available numeric anchors, careful to only use numbers present
        reasons = []
        if c.get('last') is not None:
            reasons.append(f"Latest score: {c['last']:.1f}")
        if c.get('change') is not None:
            reasons.append(f"Change (most recent): {c['change']:+.1f}")
        if c.get('benchmark_gap') is not None:
            reasons.append(f"Gap vs benchmark: {c['benchmark_gap']:+.1f}")
        if c.get('reason_tags'):
            reasons.extend(c['reason_tags'])
        why_parts = []
        if reasons:
            why_parts.append("Evidence: " + '; '.join([r for r in reasons if r]))
        why_parts.append("This area aligns to identified survey signals and may affect team performance or retention.")
        why_discuss = ' '.join(why_parts)

        # Discussion prompt: transform 'what is wrong?' into 'what should managers discuss?'
        prompt_parts = [
            f"What should managers discuss regarding {label}?",
            "Consider possible root causes, local team dynamics, and whether deeper diagnostics are needed (e.g., focus groups, manager check-ins).",
            "Avoid making final decisions here; identify topics to explore in managerial meetings."
        ]
        discussion_prompt = ' '.join(prompt_parts)

        supporting_data = c.get('supporting_data') or None
        source_fields = [s for s in (c.get('source_fields') or []) if s]

        discussion_areas.append({
            'title': title,
            'why_discuss': why_discuss,
            'discussion_prompt': discussion_prompt,
            'supporting_data': supporting_data,
            'source_fields': source_fields
        })

    # If still fewer than 2, add placeholders for missing data
    if len(discussion_areas) < 2:
        missing = ['dimensions', 'drivers', 'benchmark', 'overall_score', 'participation_rate']
        for field in missing:
            if len(discussion_areas) >= 2:
                break
            if field in (parsed.get('not_identified') or []):
                title = f"Data gap: {field} not identified"
                why_discuss = (
                    f"The parser did not identify {field} in the uploaded report. Managers should discuss whether the necessary data exists or whether parsing templates need updating."
                )
                discussion_prompt = (
                    f"What should managers discuss to confirm whether {field} is missing from the source report or needs clearer reporting?"
                )
                supporting_data = None
                discussion_areas.append({
                    'title': title,
                    'why_discuss': why_discuss,
                    'discussion_prompt': discussion_prompt,
                    'supporting_data': supporting_data,
                    'source_fields': [field]
                })

    # Ensure exactly 2 (if still less, pad with a general discussion area using overall or a neutral prompt)
    while len(discussion_areas) < 2:
        # generic area based on overall or participation
        if overall is not None:
            title = "Discuss overall engagement"
            why_discuss = f"Overall engagement is available (Overall: {overall:.1f}). Consider broad themes that may be influencing multiple dimensions."
            discussion_prompt = (
                "What should managers discuss about overall engagement trends, and which areas need deeper diagnostics?"
            )
            supporting_data = f"Overall: {overall:.1f}"
            source_fields = ['overall_score']
        elif participation is not None:
            title = "Discuss participation rate"
            why_discuss = f"Participation rate is available (Participation: {participation:.1f}%). Consider implications for data confidence and representation."
            discussion_prompt = (
                "What should managers discuss to understand participation drivers and plan ways to increase response rates?"
            )
            supporting_data = f"Participation: {participation:.1f}%"
            source_fields = ['participation_rate']
        else:
            title = "Data review: parser results"
            why_discuss = "The parser returned limited numeric data. Managers should review the source report to confirm what data is available."
            discussion_prompt = "What should managers discuss to confirm data availability and next steps for analysis?"
            supporting_data = None
            source_fields = []

        discussion_areas.append({
            'title': title,
            'why_discuss': why_discuss,
            'discussion_prompt': discussion_prompt,
            'supporting_data': supporting_data,
            'source_fields': source_fields
        })

    # Trim to exactly 2
    discussion_areas = discussion_areas[:2]

    return {
        'discussion_areas': discussion_areas,
        'meta': {
            'generated_count': len(discussion_areas)
        }
    }
