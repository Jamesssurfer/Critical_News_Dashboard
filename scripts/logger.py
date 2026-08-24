# scripts/logger.py
import os
import re
import json
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
ACTIVE_FILE = os.path.join(DATA_DIR, "active_week.json")
ARCHIVE_FILE = os.path.join(DATA_DIR, "archive.json")

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

    # --- summary: first real paragraph after the title, before a "----" divider ---
    summary = ""
    if title is not None:
        try:
            title_idx = next(i for i, l in enumerate(lines) if l.startswith('#'))
        except StopIteration:
            title_idx = 0
        for l in lines[title_idx + 1:]:
            if l.startswith('---') or l.startswith('#'):
                break
            summary = strip_markdown_links(l)
            break
    summary = summary[:280]

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

    return {
        "timestamp": timestamp,
        "category": category,
        "title": title,
        "impact_level": impact_level,
        "summary": summary
    }


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


if __name__ == "__main__":
    main()
