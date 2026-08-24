# scripts/logger.py
import os
import json
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
ACTIVE_FILE = os.path.join(DATA_DIR, "active_week.json")
ARCHIVE_FILE = os.path.join(DATA_DIR, "archive.json")

def load_data(path, default_type=list):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default_type()
    return default_type()

def save_data(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def get_event():
    p_str = os.environ.get("DISPATCH_CLIENT_PAYLOAD")
    if p_str and p_str.strip():
        try:
            p = json.loads(p_str)
            if p:
                return {
                    "timestamp": p.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "category": p.get("category", "Geopolitical"),
                    "title": p.get("title", "Alert Headline"),
                    "impact_level": p.get("impact_level", "MEDIUM"),
                    "summary": p.get("summary", "")
                }
        except:
            pass
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": os.environ.get("MANUAL_CATEGORY", "Geopolitical Risk"),
        "title": os.environ.get("MANUAL_TITLE", "Manual Execution Backup Entry"),
        "impact_level": os.environ.get("MANUAL_IMPACT", "HIGH"),
        "summary": os.environ.get("MANUAL_SUMMARY", "No dispatch payload parsed. Running script framework.")
    }

def main():
    evt = get_event()
    now = datetime.now(timezone.utc)
    
    active_items = load_data(ACTIVE_FILE, list)
    archive_dict = load_data(ARCHIVE_FILE, dict)
    
    buckets = ["past_2_weeks", "past_1_month", "past_3_months", "past_6_months", "past_1_year", "historical"]
    if not isinstance(archive_dict, dict):
        archive_dict = {}
    for b in buckets:
        if b not in archive_dict:
            archive_dict[b] = []

    combined = [evt] + active_items
    seen = set()
    unique_all = []
    for item in combined:
        uid = f"{item.get('title')}_{item.get('timestamp')}"
        if uid not in seen:
            seen.add(uid)
            unique_all.append(item)

    # Re-bucket everything based on age thresholds from current time
    new_active = []
    b_2w, b_1m, b_3m, b_6m, b_1y, b_hist = [], [], [], [], [], []

    for item in unique_all:
        try:
            dt = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
        except:
            dt = now
        age = now - dt

        if age <= timedelta(days=7):
            new_active.append(item)
        elif age <= timedelta(days=14):
            b_2w.append(item)
        elif age <= timedelta(days=30):
            b_1m.append(item)
        elif age <= timedelta(days=90):
            b_3m.append(item)
        elif age <= timedelta(days=180):
            b_6m.append(item)
        elif age <= timedelta(days=365):
            b_1y.append(item)
        else:
            b_hist.append(item)

    # Append past contents from deep storage mapping
    archive_dict["past_2_weeks"] = b_2w + archive_dict["past_2_weeks"]
    archive_dict["past_1_month"] = b_1m + archive_dict["past_1_month"]
    archive_dict["past_3_months"] = b_3m + archive_dict["past_3_months"]
    archive_dict["past_6_months"] = b_6m + archive_dict["past_6_months"]
    archive_dict["past_1_year"] = b_1y + archive_dict["past_1_year"]
    archive_dict["historical"] = b_hist + archive_dict["historical"]

    # Deduplicate and sort all chronological structural arrays from newest to oldest
    t_sort = lambda x: x.get('timestamp', '')
    new_active.sort(key=t_sort, reverse=True)
    
    for b in buckets:
        b_seen = set()
        b_dedup = []
        for item in archive_dict[b]:
            uid = f"{item.get('title')}_{item.get('timestamp')}"
            if uid not in b_seen:
                b_seen.add(uid)
                b_dedup.append(item)
        b_dedup.sort(key=t_sort, reverse=True)
        archive_dict[b] = b_dedup

    save_data(ACTIVE_FILE, new_active)
    save_data(ARCHIVE_FILE, archive_dict)

if __name__ == "__main__":
    main()
