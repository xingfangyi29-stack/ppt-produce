import re
from typing import Any, Dict, List, Optional, Tuple

# Simple regexes to extract numbers and years from strings
PERCENT_RE = re.compile(r"(\d{1,3}(?:[\.,]\d+)?)\s*%")
NUMBER_RE = re.compile(r"(-?\d{1,3}(?:[\.,]\d+)?)")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _to_float(s: str) -> Optional[float]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    # remove percent sign if present
    s = s.replace('%', '')
    try:
        return float(s.replace(',', '.'))
    except Exception:
        # fallback: find first number
        m = NUMBER_RE.search(s)
        if m:
            try:
                return float(m.group(1).replace(',', '.'))
            except Exception:
                return None
    return None


def _extract_numbers_from_cell(cell: str) -> List[float]:
    nums: List[float] = []
    if not cell:
        return nums
    # first look for percents
    for m in PERCENT_RE.finditer(cell):
        try:
            nums.append(float(m.group(1).replace(',', '.')))
        except Exception:
            continue
    # then other numbers
    for m in NUMBER_RE.finditer(cell):
        try:
            val = float(m.group(1).replace(',', '.'))
            nums.append(val)
        except Exception:
            continue
    return nums


def _find_tables_in_slides(slides: List[Dict[str, Any]]) -> List[Tuple[int, List[List[str]]]]:
    tables = []
    for s in slides:
        if s.get('tables'):
            for t in s['tables']:
                tables.append((s.get('slide_number'), t))
    return tables


def _map_table_years(table: List[List[str]]) -> Optional[List[int]]:
    # Try to detect header row that contains year labels
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
    return None


def _extract_series_from_table(table: List[List[str]]) -> Dict[str, List[Optional[float]]]:
    # Heuristic: first column is label, subsequent columns are numeric values (possibly corresponding to years)
    series: Dict[str, List[Optional[float]]] = {}
    for row in table:
        if not row:
            continue
        label = row[0].strip() if row[0] else None
        if not label:
            continue
        values: List[Optional[float]] = []
        for cell in row[1:]:
            # try to extract a primary numeric value from the cell
            nums = _extract_numbers_from_cell(cell)
            if nums:
                values.append(nums[0])
            else:
                values.append(None)
        series[label] = values
    return series


def _choose_top_insights(candidates: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    # Candidates should already have a priority field (lower is higher priority)
    sorted_c = sorted(candidates, key=lambda x: x.get('priority', 100))
    return sorted_c[:limit]


def generate_insights(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate 1-3 concise insights from parsed survey data.

    The function is rule-based and NEVER invents numbers. All numeric claims are based
    on numbers found in the parsed input. If insufficient data is available for an
    insight, that insight is NOT created.

    Input: parsed (the output from the parser)
    Output: { "insights": [ { title, what_happened, why_it_matters, supporting_data, source_fields } ], "meta": {...} }
    """
    insights: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []

    # Helper shortcuts
    overall = parsed.get('overall_score')
    benchmark = parsed.get('benchmark')
    participation = parsed.get('participation_rate')
    years = parsed.get('years') or []
    slides = parsed.get('slides') or []
    dimensions = parsed.get('dimensions') or []

    # 1) Benchmark gap insight (priority 1)
    if overall is not None and benchmark is not None:
        gap = benchmark - overall
        if abs(gap) >= 3:  # threshold in points
            title = 'Benchmark gap in Overall Engagement'
            direction = 'below' if gap > 0 else 'above'
            what = f"Overall engagement is {abs(gap):.1f} points {direction} the benchmark (Overall: {overall:.1f}, Benchmark: {benchmark:.1f})."
            why = (
                "A material gap versus the benchmark indicates competitive weakness or strength relative to peers. "
                "This helps prioritize strategic focus areas and external benchmarking discussions."
            )
            supporting = f"Overall: {overall:.1f}; Benchmark: {benchmark:.1f}; Gap: {gap:.1f}"
            source_fields = ['overall_score', 'benchmark']
            candidates.append({
                'priority': 1,
                'title': title,
                'what_happened': what,
                'why_it_matters': why,
                'supporting_data': supporting,
                'source_fields': source_fields
            })

    # 2) Participation signal (priority 2)
    # Low participation absolute threshold or sharp decline across years
    if participation is not None:
        if participation < 50:
            title = 'Low participation rate'
            what = f"Participation rate is low at {participation:.1f}% which may reduce confidence in the representativeness of results."
            why = (
                "Low participation can bias results and limit confidence in conclusions. Consider actions to increase response rates before major decisions."
            )
            supporting = f"Participation rate: {participation:.1f}%"
            source_fields = ['participation_rate']
            candidates.append({
                'priority': 2,
                'title': title,
                'what_happened': what,
                'why_it_matters': why,
                'supporting_data': supporting,
                'source_fields': source_fields
            })

    # Check for participation trend across slides/tables if years present
    # Extract any per-year participation series from tables/text
    participation_series = None
    # Look for slides that have 'found_participation' or table rows with 'participat'
    per_year_participation = {}
    for s in slides:
        if s.get('found_participation') is not None and s.get('years'):
            # map year -> value using s['years'] array and found_participation as single?
            # This heuristic treats found_participation as the most recent value
            for y in s['years']:
                per_year_participation[y] = s.get('found_participation')
        # inspect tables
        if s.get('tables'):
            for t in s['tables']:
                # try to detect header years
                header_years = None
                # check first 2 rows
                for row in t[:2]:
                    # look for any year in row
                    header_years = []
                    for cell in row:
                        if cell:
                            m = YEAR_RE.search(cell)
                            if m:
                                try:
                                    header_years.append(int(m.group(0)))
                                except Exception:
                                    pass
                    if header_years:
                        break
                if not header_years:
                    header_years = years
                # try to find a row labeled 'Participation' or similar
                for row in t:
                    if not row:
                        continue
                    label = row[0] or ''
                    if 'participat' in label.lower() or 'response rate' in label.lower():
                        for i, cell in enumerate(row[1:1+len(header_years)]):
                            num = _to_float(cell)
                            if num is not None and header_years and i < len(header_years):
                                per_year_participation[header_years[i]] = num
    if per_year_participation:
        # check for drop
        ys = sorted(per_year_participation.keys())
        if len(ys) >= 2:
            last = per_year_participation[ys[-1]]
            prev = per_year_participation[ys[-2]]
            if last is not None and prev is not None:
                decline = prev - last
                if decline >= 10:  # arbitrary threshold
                    title = 'Participation declined significantly'
                    what = f"Participation declined from {prev:.1f}% in {ys[-2]} to {last:.1f}% in {ys[-1]} ({decline:.1f} points)."
                    why = (
                        "A sharp drop in participation reduces result reliability and may signal engagement or communication issues. Investigate reasons and consider targeted outreach."
                    )
                    supporting = f"{ys[-2]}: {prev:.1f}%; {ys[-1]}: {last:.1f}%"
                    source_fields = [f"slides (participation table) - years: {ys[-2]},{ys[-1]}"]
                    candidates.append({
                        'priority': 2,
                        'title': title,
                        'what_happened': what,
 'why_it_matters': why,
                        'supporting_data': supporting,
                        'source_fields': source_fields
                    })

    # 3) Significant change in overall or dimensions (priority 1)
    # Try to extract a time series for Overall Engagement
    overall_series = None
    overall_series_source = None

    # search tables for a row labeled overall/engagement
    tables = _find_tables_in_slides(slides)
    for slide_num, table in tables:
        # detect header years
        header_years = _map_table_years(table) or years
        series = _extract_series_from_table(table)
        for label, vals in series.items():
            if label and 'overall' in label.lower() and any(v is not None for v in vals):
                # map values to header_years
                if header_years and len(header_years) >= len(vals):
                    paired = [(header_years[i], vals[i] if i < len(vals) else None) for i in range(min(len(header_years), len(vals)))]
                else:
                    # fallback: assign sequential years if available
                    paired = list(enumerate(vals))
                # convert to numbers
                cleaned = [(y, float(v)) for (y, v) in paired if v is not None]
                if len(cleaned) >= 2:
                    overall_series = cleaned
                    overall_series_source = f"table on slide {slide_num} (row: {label})"
                    break
        if overall_series:
            break

    # If we have an overall series, check last two points for significant change
    if overall_series and len(overall_series) >= 2:
        ys = [y for y, _ in overall_series]
        vals = [v for _, v in overall_series]
        last = vals[-1]
        prev = vals[-2]
        change = last - prev
        if abs(change) >= 5:  # significant threshold
            direction = 'increased' if change > 0 else 'declined'
            title = f'Overall engagement {"increased" if change>0 else "declined"} by {abs(change):.1f} points'
            what = f"Overall engagement {direction} from {prev:.1f} in {ys[-2]} to {last:.1f} in {ys[-1]} ({change:+.1f})."
            why = (
                "A material year-on-year change in overall engagement is noteworthy for leadership — it may indicate the impact of recent initiatives or emerging risks."
            )
            supporting = f"{ys[-2]}: {prev:.1f}; {ys[-1]}: {last:.1f}; Change: {change:+.1f}"
            source_fields = [overall_series_source]
            candidates.append({
                'priority': 1,
                'title': title,
                'what_happened': what,
                'why_it_matters': why,
                'supporting_data': supporting,
                'source_fields': source_fields
            })

    # 4) Consistent trend across >=3 years for a dimension or overall (priority 3)
    # Search for dimension series (rows where first cell matches known dimension names or looks like a label)
    dimension_series_found = []
    for slide_num, table in tables:
        header_years = _map_table_years(table) or years
        series = _extract_series_from_table(table)
        for label, vals in series.items():
            if not label:
                continue
            # skip overall (handled)
            if 'overall' in label.lower():
                continue
            cleaned = []
            for i, v in enumerate(vals):
                if v is not None:
                    # map to year if present
                    year = None
                    if header_years and i < len(header_years):
                        year = header_years[i]
                    cleaned.append((year, float(v)))
            if len(cleaned) >= 3:
                # check monotonic trend
                vals_only = [v for _, v in cleaned]
                inc = all(x < y for x, y in zip(vals_only, vals_only[1:]))
                dec = all(x > y for x, y in zip(vals_only, vals_only[1:]))
                total_change = vals_only[-1] - vals_only[0]
                if (inc or dec) and abs(total_change) >= 5:
                    direction = 'increasing' if inc else 'decreasing'
                    title = f'{label} shows a consistent {direction} trend'
                    years_used = [y for y, _ in cleaned if y is not None]
                    what = f"{label} moved from {vals_only[0]:.1f} in {years_used[0] if years_used else 'earlier'} to {vals_only[-1]:.1f} in {years_used[-1] if years_used else 'latest'} ({total_change:+.1f})."
                    why = (
                        "A consistent multi-year trend suggests a sustained shift in experience for this area, which may require strategic attention."
                    )
                    supporting = f"{years_used[0] if years_used else 'start'}: {vals_only[0]:.1f}; {years_used[-1] if years_used else 'end'}: {vals_only[-1]:.1f}; Change: {total_change:+.1f}"
                    source_fields = [f"table on slide {slide_num} (row: {label})"]
                    candidates.append({
                        'priority': 3,
                        'title': title,
                        'what_happened': what,
                        'why_it_matters': why,
                        'supporting_data': supporting,
                        'source_fields': source_fields
                    })

    # 5) Unexpected results: dimensions far from overall
    if overall is not None and tables:
        for slide_num, table in tables:
            series = _extract_series_from_table(table)
            for label, vals in series.items():
                if not label:
                    continue
                if 'overall' in label.lower():
                    continue
                # try last value
                if not vals:
                    continue
                last_vals = [v for v in vals if v is not None]
                if not last_vals:
                    continue
                last = last_vals[-1]
                if last is None:
                    continue
                diff = last - overall
                if abs(diff) >= 10:
                    # flag if much higher or lower
                    direction = 'higher' if diff > 0 else 'lower'
                    title = f'{label} is {abs(diff):.1f} points {direction} than overall engagement'
                    what = f"{label} scored {last:.1f}, which is {abs(diff):.1f} points {direction} than the overall engagement ({overall:.1f})."
                    why = (
                        "A large deviation from overall may indicate a specific area of distinct strength or concern that deserves targeted focus."
                    )
                    supporting = f"{label}: {last:.1f}; Overall: {overall:.1f}; Diff: {diff:+.1f}"
                    source_fields = [f"table on slide {slide_num} (row: {label})", 'overall_score']
                    candidates.append({
                        'priority': 4,
                        'title': title,
                        'what_happened': what,
                        'why_it_matters': why,
                        'supporting_data': supporting,
                        'source_fields': source_fields
                    })

    # Select up to 3 insights by priority
    chosen = _choose_top_insights(candidates, limit=3)

    # Format final insights ensuring fields exist and are concise
    final_insights: List[Dict[str, Any]] = []
    for c in chosen:
        insight = {
            'title': c['title'],
            'what_happened': c['what_happened'],
            'why_it_matters': c['why_it_matters'],
            'supporting_data': c['supporting_data'],
            'source_fields': c.get('source_fields', [])
        }
        final_insights.append(insight)

    meta = {
        'count': len(final_insights),
        'rules_used': ['benchmark_gap', 'participation_signal', 'significant_change', 'consistent_trend', 'unexpected_diff']
    }

    return {
        'insights': final_insights,
        'meta': meta
    }
