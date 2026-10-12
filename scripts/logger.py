# scripts/logger.py — Critical News / Macro Risk Intelligence Alert logger
#
# Parses pasted "Macro Risk & Geopolitical Intelligence Alert" blobs
# (timestamp line, ## lead narrative, risk matrix table, deep-dive sections,
# strategic advice) into structured JSON for the dashboard.
#
# Fix vs prior version: the main narrative lived inside the ## heading and
# was truncated mid-word at 200 chars for the title, while first_paragraph
# stayed empty. The full lead is now kept in details; title is a clean
# short teaser truncated at a word boundary.

import os
import re
import json
from datetime import datetime, timedelta, timezone
from collections import Counter

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
    if not text:
        return ""
    # Normal [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Broken forms: text[](url) or [](url)
    text = re.sub(r'\[\]\([^)]+\)', '', text)
    # Bare URLs in parens left over
    text = re.sub(r'\(https?://[^)]+\)', '', text)
    # Heading markers
    text = re.sub(r'^\#+\s*', '', text)
    text = text.replace('**', '').replace('__', '')
    # Collapse whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def strip_emoji_prefix(text: str) -> str:
    return re.sub(r'^[^\w\s]+\s*', '', text).strip()


def truncate_at_word(text: str, max_len: int = 180) -> str:
    """Truncate at a word boundary so titles never end mid-word."""
    if not text or len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(' ', 1)[0].rstrip('.,;:—–-')
    return cut + "…"


def first_sentence(text: str, max_len: int = 220) -> str:
    """Prefer a clean first sentence; fall back to word-boundary truncate."""
    if not text:
        return ""
    protected = text
    for abbr in ("U.S.", "U.K.", "U.N.", "E.U.", "e.g.", "i.e.", "vs.", "Mr.", "Mrs.", "Ms.", "Dr.", "C$", "IRGC"):
        protected = protected.replace(abbr, abbr.replace(".", "\uff0e"))
    m = re.match(r'^([^.!?]+[.!?])', protected)
    if m:
        sent = m.group(1).replace("\uff0e", ".").strip()
        if 40 <= len(sent) <= max_len:
            return sent
        if len(sent) > max_len:
            return truncate_at_word(sent, max_len)
    return truncate_at_word(text, max_len)


CATEGORY_KEYWORDS = {
    "Trade War": ["tariff", "trade war", "trade friction", "export control", "sanction", "cepa", "trade pact", "trade mission"],
    "Currency": ["dxy", "boj", "fed ", "federal reserve", "yen", "jpy", "usd/jpy", "interest rate",
                 "rate check", "rate hike", "rate cut", "central bank", "treasury yield"],
}

IMPACT_EMOJI = {"🔴": "HIGH", "🟠": "HIGH", "🟡": "MEDIUM", "🟢": "LOW", "⚪": "LOW"}

IMPACT_KEYWORDS = {
    "HIGH": ["critical", "severe", "escalat", "urgent", "historic", "unprecedented", "kill box", "blockade"],
    "MEDIUM": ["elevated", "moderate", "monitor"],
    "LOW": ["stable", "low risk", "contained"],
}

DXY_SHORT_KEYWORDS = ["boj", "yen buying", "jpy buying", "rate check", "treasury buyback",
                      "liquidity operation", "dovish", "rate cut"]
DXY_LONG_KEYWORDS = ["rate hike", "hawkish", "strong dollar", "fed tightening"]
OIL_BULLISH_KEYWORDS = ["drone", "tanker", "strait", "energy corridor", "pipeline attack",
                        "oil field", "refinery strike", "energy infrastructure", "hormuz",
                        "bab el-mandeb", "clarksea", "vlcc", "freight"]
SAFE_HAVEN_KEYWORDS = ["military", "strike", "conflict", "war", "escalat", "tension",
                       "invasion", "attack", "missile", "kinetic", "blockade"]


def infer_market_read(category: str, impact_level: str, raw_lower: str) -> str:
    dxy_bias = None
    if category == "Currency":
        if any(kw in raw_lower for kw in DXY_SHORT_KEYWORDS):
            dxy_bias = "short"
        elif any(kw in raw_lower for kw in DXY_LONG_KEYWORDS):
            dxy_bias = "long"
    oil_bullish = any(kw in raw_lower for kw in OIL_BULLISH_KEYWORDS)
    safe_haven = any(kw in raw_lower for kw in SAFE_HAVEN_KEYWORDS)

    if dxy_bias:
        xau_bias = "long" if dxy_bias == "short" else "short"
        return f"Market read: DXY {dxy_bias} / XAU {xau_bias}."
    if oil_bullish and safe_haven:
        return "Market read: Oil bullish / XAU long."
    if oil_bullish:
        return "Market read: Oil bullish / freight premium."
    if category == "Trade War":
        return "Market read: XAU long catalyst."
    if safe_haven or impact_level == "HIGH":
        return "Market read: XAU long (safe-haven flow)."
    if impact_level == "MEDIUM":
        return "Market read: XAU catalyst — monitor."
    return "Market read: XAU neutral."


def extract_table(lines):
    """Parse the first markdown table into structured rows."""
    for i in range(len(lines) - 1):
        line = lines[i]
        nxt = lines[i + 1]
        if not (line.startswith('|') and '|' in line[1:] and nxt.startswith('|')):
            continue
        sep_check = set(nxt.replace('|', '').replace('-', '').replace(':', '').strip())
        if sep_check:
            continue
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
                    "detail": detail,
                })
        return table_rows
    return []


def _split_stories(raw_text: str):
    """Split a multi-alert paste on === delimiters."""
    normalized = raw_text.replace("\r\n", "\n")
    parts = re.split(r'\n===\n|^===\n|\n===$', normalized)
    return [p.strip() for p in parts if p.strip()]


def parse_raw_text(raw: str) -> dict | None:
    """
    Best-effort parser for Macro Risk & Geopolitical Intelligence Alert blobs.
    """
    if not raw or not raw.strip():
        return None

    # Keep original lines for structure; also a stripped list for scanning
    raw_lines = raw.replace("\r\n", "\n").splitlines()
    lines = [l.strip() for l in raw_lines if l.strip()]
    if not lines:
        return None

    # --- timestamp: "October 8, 1:47 AM" or "October 11, 7:50 PM" near top ---
    timestamp = None
    for l in lines[:5]:
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

    # --- lead narrative: the ## 🚨 ... line (full paragraph, NOT truncated) ---
    lead = ""
    title_idx = None
    for i, l in enumerate(lines):
        if l.startswith('#'):
            lead = strip_emoji_prefix(strip_markdown_links(l))
            title_idx = i
            break
    if not lead:
        for i, l in enumerate(lines):
            if len(l) > 40 and not l.lower().startswith("macro risk"):
                lead = strip_emoji_prefix(strip_markdown_links(l))
                title_idx = i
                break
    if not lead:
        lead = lines[0][:300]

    # Card title = clean first sentence / word-boundary teaser (never mid-word)
    title = first_sentence(lead, max_len=200)

    # --- category ---
    lower = raw.lower()
    category = "Geopolitical"
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            category = cat
            break

    # --- impact ---
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

    summary = infer_market_read(category, impact_level, lower)

    # --- details: FULL lead first, then deep-dive sections ---
    # Skip: matrix table, dividers, empty bullets, footer boilerplate, citations
    details_blocks = []
    if lead:
        details_blocks.append(lead)

    skip_matrix = False
    start = (title_idx + 1) if title_idx is not None else 0
    for l in lines[start:]:
        low_l = l.lower()

        # Hard stop before interactive / pipeline boilerplate
        if any(phrase in low_l for phrase in (
            'automated pipeline status',
            'i will stay on top',
            'i am keeping',
            'the alert console is locked',
            'to help guide your absolute tactical stance',
            'let me know if you would like me to',
            'as the live',
            'as global',
            'please let me know in this conversation',
            'to optimize the precision of the incoming micro-alerts',
        )):
            break

        # Citation footer lines like [1] https://...
        if re.match(r'^\[\d+\]\s*', l) or re.match(r'^https?://', l):
            continue

        # Tactical Risk Matrix block (table extracted separately)
        if 'tactical risk matrix' in low_l:
            skip_matrix = True
            continue
        if skip_matrix:
            if l.startswith('##') and 'tactical risk matrix' not in low_l:
                skip_matrix = False
                # fall through — this is the next deep-dive heading
            else:
                if l.startswith('```') or l.startswith('|') or l.startswith('---'):
                    continue
                continue

        if l.startswith('---') or l.startswith('|') or l.startswith('```'):
            continue
        # Empty markdown bullets
        if l in ('*', '-', '•'):
            continue

        stripped = strip_markdown_links(l)
        if not stripped:
            continue
        # Skip pure document-type headers already known
        if stripped.lower() in (
            'macro risk & geopolitical intelligence alert',
            'intelligence deep dive & core developments',
            'strategic advice & market actions',
        ):
            # Keep section headings that are useful (deep dive / advice)
            if 'deep dive' in stripped.lower() or 'strategic advice' in stripped.lower():
                details_blocks.append(stripped)
            continue

        # Split glued ## headings on one line
        if '##' in stripped:
            parts = re.split(r'\s*##+\s*', stripped)
            for p in parts:
                p = strip_emoji_prefix(p.strip())
                if p and p != lead:
                    details_blocks.append(p)
            continue

        # Avoid duplicating the lead
        if stripped == lead or (lead and stripped.startswith(lead[:80])):
            continue

        details_blocks.append(stripped)

    # Join with blank lines between blocks for readability
    details = "\n\n".join(d for d in details_blocks if d)

    # Soft cap at word/paragraph boundary (was hard-cutting mid-narrative)
    if len(details) > 16000:
        details = details[:16000].rsplit('\n\n', 1)[0]

    table = extract_table(lines)

    return {
        "timestamp": timestamp,
        "category": category,
        "title": title,
        "impact_level": impact_level,
        "summary": summary,
        "details": details,
        "table": table,
    }


def compute_triggers(recent_items, max_triggers=4, recency_days=14):
    now = datetime.now(timezone.utc)
    recent = []
    for item in recent_items:
        try:
            dt = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
        except Exception:
            continue
        if now - dt <= timedelta(days=recency_days):
            recent.append(item)

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
            "impact_level": c.get('impact_level', ''),
        })
    return triggers


def get_events():
    """
    Returns a list of new event dicts, or [] if this run should not inject
    any new items (scheduled rebucket-only, empty payload, etc.).
    """
    if os.environ.get("REBUCKET_ONLY") == "1":
        return []

    events = []

    p_str = os.environ.get("DISPATCH_CLIENT_PAYLOAD")
    if p_str and p_str.strip():
        try:
            p = json.loads(p_str)
        except Exception:
            p = None
        if isinstance(p, dict):
            texts = []
            if p.get("raw_text_list"):
                texts.extend(p["raw_text_list"])
            elif p.get("raw_text"):
                texts.append(p["raw_text"])

            for raw in texts:
                # Support multi-alert pastes separated by ===
                for block in _split_stories(raw):
                    parsed = parse_raw_text(block)
                    if parsed:
                        events.append(parsed)

            if events:
                return events

            # Structured payload fallback (no raw_text)
            if p.get("title"):
                return [{
                    "timestamp": p.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "category": p.get("category", "Geopolitical"),
                    "title": p.get("title", "Alert Headline"),
                    "impact_level": p.get("impact_level", "MEDIUM"),
                    "summary": p.get("summary", ""),
                    "details": p.get("details", ""),
                    "table": p.get("table", []),
                }]

    manual_title = os.environ.get("MANUAL_TITLE")
    if manual_title:
        return [{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": os.environ.get("MANUAL_CATEGORY", "Geopolitical Risk"),
            "title": manual_title,
            "impact_level": os.environ.get("MANUAL_IMPACT", "HIGH"),
            "summary": os.environ.get("MANUAL_SUMMARY", ""),
            "details": os.environ.get("MANUAL_DETAILS", ""),
            "table": [],
        }]

    # Manual raw_text form field
    manual_raw = os.environ.get("MANUAL_RAW_TEXT")
    if manual_raw and manual_raw.strip():
        for block in _split_stories(manual_raw):
            parsed = parse_raw_text(block)
            if parsed:
                events.append(parsed)
        return events

    return []


def bucket_for_age(age: timedelta):
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
    new_events = get_events()
    now = datetime.now(timezone.utc)

    active_items = load_data(ACTIVE_FILE, list)
    archive_dict = load_data(ARCHIVE_FILE, dict)
    if not isinstance(archive_dict, dict):
        archive_dict = {}
    for b in BUCKETS:
        if b not in archive_dict:
            archive_dict[b] = []

    pool = list(new_events)
    pool.extend(active_items)
    for b in BUCKETS:
        pool.extend(archive_dict[b])

    seen = set()
    unique_all = []
    for item in pool:
        uid = f"{item.get('title')}_{item.get('timestamp')}"
        if uid not in seen:
            seen.add(uid)
            unique_all.append(item)

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
