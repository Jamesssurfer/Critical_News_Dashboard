# scripts/logger.py
import os
import re
import json
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
ACTIVE_FILE = os.path.join(DATA_DIR, "active_week.json")
ARCHIVE_FILE = os.path.join(DATA_DIR, "archive.json")
TRIGGERS_FILE = os.path.join(DATA_DIR, "triggers.json")

BUCKETS = ["past_2_weeks", "past_1_month", "past_3_months", "past_6_months", "past_1_year", "historical"]


def load_data(path, default_type=list):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default_type()
    return default_type()


def save_data(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def strip_markdown_links(text: str) -> str:
    # [Israel](https://...) -> Israel
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # remove leftover markdown emphasis/heading markers
    text = re.sub(r'^\#+\s*', '', text)
    text = text.replace('**', '').replace('__', '')
    return text.strip()


def strip_emoji_prefix(text: str) -> str:
    # Drop a leading emoji + following space (e.g. "🚨 Headline" -> "Headline")
    return re.sub(r'^[^\w\s]+\s*', '', text).strip()


CATEGORY_KEYWORDS = {
    "Trade War": ["tariff", "trade war", "trade friction", "export control", "sanction"],
    "Currency": ["dxy", "boj", "fed ", "federal reserve", "yen", "jpy", "usd", "dollar",
                 "interest rate", "rate check", "rate hike", "rate cut", "central bank"],
}

IMPACT_EMOJI = {"🔴": "HIGH", "🟠": "HIGH", "🟡": "MEDIUM", "🟢": "LOW", "⚪": "LOW"}
IMPACT_KEYWORDS = {
    "HIGH": ["critical", "severe", "escalat", "urgent"],
    "MEDIUM": ["elevated", "moderate", "monitor"],
    "LOW": ["stable", "low risk", "contained"],
}


# Best-effort keyword rules for a "Market read: ..." style line, matching
# the format of the original preset entries. This is pattern-matching on
# wording, NOT real market analysis — it will be wrong on anything that
# doesn't map cleanly to these patterns. Treat every generated line as a
# draft to check, not a signal to trade on.
DXY_SHORT_KEYWORDS = ["boj", "yen buying", "jpy buying", "rate check", "treasury buyback",
                      "liquidity operation", "dovish", "rate cut"]
DXY_LONG_KEYWORDS = ["rate hike", "hawkish", "strong dollar", "fed tightening"]
OIL_BULLISH_KEYWORDS = ["drone", "tanker", "strait", "energy corridor", "pipeline attack",
                        "oil field", "refinery strike", "energy infrastructure"]
SAFE_HAVEN_KEYWORDS = ["military", "strike", "conflict", "war", "escalat", "tension",
                       "invasion", "attack", "missile"]


def infer_market_read(category: str, impact_level: str, raw_lower: str) -> str:
    dxy_bias = None
    if category == "Currency":
        if any(kw in raw_lower for kw in DXY_SHORT_KEYWORDS):
            dxy_bias = "short"
        elif any(kw in raw_lower for kw in DXY_LONG_KEYWORDS):
            dxy_bias = "long"

    oil_bullish = category == "Geopolitical" and any(kw in raw_lower for kw in OIL_BULLISH_KEYWORDS)
    safe_haven = any(kw in raw_lower for kw in SAFE_HAVEN_KEYWORDS)

    if dxy_bias:
        xau_bias = "long" if dxy_bias == "short" else "short"
        return f"Market read: DXY {dxy_bias} / XAU {xau_bias}."

    if oil_bullish:
        return "Market read: Oil bullish / XAU long."

    if category == "Trade War":
        return "Market read: XAU long catalyst."

    if safe_haven or impact_level == "HIGH":
        return "Market read: XAU long (safe-haven flow)."

    if impact_level == "MEDIUM":
        return "Market read: XAU catalyst — monitor."

    return "Market read: XAU neutral."


def extract_table(lines):
    """
    Finds the first markdown table (header row, |---|---|---| separator,
    data rows) and parses it into structured rows. Returns [] if no
    table is found. Only the first table in the text is captured — a
    story with two separate tables will lose the second one, same as
    today's behavior of skipping table rows entirely.
    """
    for i in range(len(lines) - 1):
        line = lines[i]
        nxt = lines[i + 1]
        if not (line.startswith('|') and line.endswith('|') and nxt.startswith('|')):
            continue
        # separator row is only made of |, -, :, and spaces
        sep_check = set(nxt.replace('|', '').replace('-', '').replace(':', '').strip())
        if sep_check:
            continue

        header_cells = [c.strip() for c in line.strip('|').split('|')]
        rows = []
        j = i + 2
        while j < len(lines) and lines[j].startswith('|'):
            data_cells = [c.strip() for c in lines[j].strip('|').split('|')]
            rows.append(data_cells)
            j += 1

        table_rows = []
        for cells in rows:
            indicator = strip_markdown_links(cells[0]) if len(cells) > 0 else ''
            signal_raw = cells[1] if len(cells) > 1 else ''
            signal_level = None
            for emoji, lvl in IMPACT_EMOJI.items():
                if emoji in signal_raw:
                    signal_level = lvl
                    break
            signal_label = strip_emoji_prefix(strip_markdown_links(signal_raw))
            detail = strip_markdown_links(' '.join(cells[2:])) if len(cells) > 2 else ''
            if indicator or signal_label or detail:
                table_rows.append({
                    "indicator": indicator,
                    "signal_level": signal_level,
                    "signal_label": signal_label,
                    "detail": detail
                })
        return table_rows
    return []


def parse_raw_text(raw: str) -> dict | None:
    """
    Best-effort parser for a pasted news/briefing blob (e.g. Google AI Mode
    output). Not guaranteed to be perfectly accurate on formats it hasn't
    seen — if the result looks wrong, fix it directly in the JSON or
    re-run workflow_dispatch using the structured fields instead.
    """
    if not raw or not raw.strip():
        return None

    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return None

    # --- timestamp: look for a "Month DD, H:MM AM/PM" line near the top ---
    timestamp = None
    for l in lines[:3]:
        m = re.search(r'([A-Z][a-z]+ \d{1,2},\s*\d{1,2}:\d{2}\s*[AaPp][Mm])', l)
        if m:
            try:
                now = datetime.now(timezone.utc)
                dt = datetime.strptime(f"{m.group(1)} {now.year}", "%B %d, %I:%M %p %Y")
                timestamp = dt.replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
            break
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    # --- title: first markdown heading ("## ...") line, else first long line ---
    title = None
    for l in lines:
        if l.startswith('#'):
            title = strip_emoji_prefix(strip_markdown_links(l))
            break
    if title is None:
        for l in lines:
            if len(l) > 25:
                title = strip_emoji_prefix(strip_markdown_links(l))
                break
    if title is None:
        title = lines[0][:120]
    title = title.rstrip('.')[:200]

    # --- first_paragraph: the descriptive text right after the title,
    #     before a "----" divider. No longer shown as the row summary
    #     (market-read line takes that spot) — feeds into 'details' below. ---
    first_paragraph = ""
    try:
        title_idx = next(i for i, l in enumerate(lines) if l.startswith('#'))
    except StopIteration:
        title_idx = 0
    for l in lines[title_idx + 1:]:
        if l.startswith('---') or l.startswith('#'):
            break
        first_paragraph = strip_markdown_links(l)
        break

    # --- category: keyword match over the whole blob ---
    lower = raw.lower()
    category = "Geopolitical"
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            category = cat
            break

    # --- impact: first status emoji found, else keyword match, else MEDIUM ---
    impact_level = None
    for emoji, level in IMPACT_EMOJI.items():
        if emoji in raw:
            impact_level = level
            break
    if impact_level is None:
        for level, kws in IMPACT_KEYWORDS.items():
            if any(kw in lower for kw in kws):
                impact_level = level
                break
    if impact_level is None:
        impact_level = "MEDIUM"

    original_paragraph = first_paragraph
    summary = infer_market_read(category, impact_level, lower)

    # --- details: fuller body text, starting with the original paragraph,
    #     then the rest of the analysis sections, stopping before the
    #     "Automated Pipeline Status" boilerplate. Used for an expandable
    #     "read more" view since summary above is now the short market-read
    #     line, not the description. ---
    details_lines = [original_paragraph] if original_paragraph else []
    try:
        title_idx = next(i for i, l in enumerate(lines) if l.startswith('#'))
    except StopIteration:
        title_idx = 0
    for l in lines[title_idx + 1:]:
        low_l = l.lower()
        if 'automated pipeline status' in low_l or 'i am keeping' in low_l:
            break
        if l.startswith('---') or l.startswith('|') or l == '*':
            continue
        stripped = strip_markdown_links(l)
        if stripped == original_paragraph:
            continue
        details_lines.append(stripped)
    details = "\n\n".join(d for d in details_lines if d)[:4000]

    table = extract_table(lines)

    return {
        "timestamp": timestamp,
        "category": category,
        "title": title,
        "impact_level": impact_level,
        "summary": summary,
        "details": details,
        "table": table
    }


def compute_triggers(recent_items, max_triggers=4, recency_days=14):
    """
    Fully automatic — no human approval step. Rule-based, not a synthesized
    theme name: picks the most recent headline from whichever categories
    are currently 'hot' — either a HIGH-impact item, or a category that's
    shown up 2+ times recently (a repeated cluster). One badge per category
    max, most urgent first. This will read more like a headline ticker than
    the hand-written thematic phrases it replaces — that's the honest
    ceiling of doing this without an LLM call in the loop.
    """
    now = datetime.now(timezone.utc)
    recent = []
    for item in recent_items:
        try:
            dt = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
        except Exception:
            continue
        if now - dt <= timedelta(days=recency_days):
            recent.append(item)

    from collections import Counter
    cat_counts = Counter(i.get('category', '') for i in recent)

    def sort_key(i):
        return i.get('timestamp', '')

    high_items = sorted(
        [i for i in recent if i.get('impact_level') == 'HIGH'],
        key=sort_key, reverse=True
    )
    cluster_categories = {c for c, n in cat_counts.items() if n >= 2}

    candidates = []
    seen_categories = set()

    for i in high_items:
        cat = i.get('category', '')
        if cat not in seen_categories:
            candidates.append(i)
            seen_categories.add(cat)
        if len(candidates) >= max_triggers:
            break

    if len(candidates) < max_triggers:
        for cat in cluster_categories:
            if cat in seen_categories:
                continue
            cat_items = sorted(
                [i for i in recent if i.get('category', '') == cat],
                key=sort_key, reverse=True
            )
            if cat_items:
                candidates.append(cat_items[0])
                seen_categories.add(cat)
            if len(candidates) >= max_triggers:
                break

    triggers = []
    for c in candidates[:max_triggers]:
        label = c.get('title', '')[:90]
        triggers.append({
            "label": label,
            "category": c.get('category', ''),
            "impact_level": c.get('impact_level', '')
        })
    return triggers


def get_event():
    """
    Returns a new event dict, or None if this run should not inject
    any new item (e.g. a scheduled rebucket-only run, or a dispatch
    with no usable payload).
    """
    # Scheduled runs exist ONLY to re-age existing data. Never fabricate
    # an event on these.
    if os.environ.get("REBUCKET_ONLY") == "1":
        return None

    p_str = os.environ.get("DISPATCH_CLIENT_PAYLOAD")
    if p_str and p_str.strip():
        try:
            p = json.loads(p_str)
            if p:
                if p.get("raw_text_list"):
                    parsed_list = [parse_raw_text(rt) for rt in p["raw_text_list"]]
                    parsed_list = [x for x in parsed_list if x]
                    if parsed_list:
                        return parsed_list
                if p.get("raw_text"):
                    parsed = parse_raw_text(p["raw_text"])
                    if parsed:
                        return parsed
                return {
                    "timestamp": p.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "category": p.get("category", "Geopolitical"),
                    "title": p.get("title", "Alert Headline"),
                    "impact_level": p.get("impact_level", "MEDIUM"),
                    "summary": p.get("summary", "")
                }
        except Exception:
            pass

    # Manual workflow_dispatch path (person filled in the Actions form).
    manual_title = os.environ.get("MANUAL_TITLE")
    if manual_title:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": os.environ.get("MANUAL_CATEGORY", "Geopolitical Risk"),
            "title": manual_title,
            "impact_level": os.environ.get("MANUAL_IMPACT", "HIGH"),
            "summary": os.environ.get("MANUAL_SUMMARY", "")
        }

    # No dispatch payload, no manual inputs, not rebucket-only -> nothing to log.
    return None


def bucket_for_age(age: timedelta) -> str | None:
    """Returns None if item belongs in active_week (age <= 7 days)."""
    if age <= timedelta(days=7):
        return None
    if age <= timedelta(days=14):
        return "past_2_weeks"
    if age <= timedelta(days=30):
        return "past_1_month"
    if age <= timedelta(days=90):
        return "past_3_months"
    if age <= timedelta(days=180):
        return "past_6_months"
    if age <= timedelta(days=365):
        return "past_1_year"
    return "historical"


def main():
    evt = get_event()
    now = datetime.now(timezone.utc)

    active_items = load_data(ACTIVE_FILE, list)
    archive_dict = load_data(ARCHIVE_FILE, dict)
    if not isinstance(archive_dict, dict):
        archive_dict = {}
    for b in BUCKETS:
        if b not in archive_dict:
            archive_dict[b] = []

    # Pull EVERYTHING — active items, every archive bucket, and the new
    # event (if any) — into one pool. This is what fixes archived items
    # never re-aging: every item is re-evaluated against `now` on every run.
    pool = []
    if evt:
        if isinstance(evt, list):
            pool.extend(evt)
        else:
            pool.append(evt)
    pool.extend(active_items)
    for b in BUCKETS:
        pool.extend(archive_dict[b])

    # Dedupe across the whole pool
    seen = set()
    unique_all = []
    for item in pool:
        uid = f"{item.get('title')}_{item.get('timestamp')}"
        if uid not in seen:
            seen.add(uid)
            unique_all.append(item)

    # Re-bucket everything from scratch based on current age
    new_active = []
    new_archive = {b: [] for b in BUCKETS}

    for item in unique_all:
        try:
            dt = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
        except Exception:
            dt = now
        age = now - dt
        b = bucket_for_age(age)
        if b is None:
            new_active.append(item)
        else:
            new_archive[b].append(item)

    t_sort = lambda x: x.get('timestamp', '')
    new_active.sort(key=t_sort, reverse=True)
    for b in BUCKETS:
        new_archive[b].sort(key=t_sort, reverse=True)

    save_data(ACTIVE_FILE, new_active)
    save_data(ARCHIVE_FILE, new_archive)

    trigger_pool = new_active + new_archive.get("past_2_weeks", [])
    triggers = compute_triggers(trigger_pool)
    save_data(TRIGGERS_FILE, triggers)


if __name__ == "__main__":
    main()
