import os
import sys
import json
import requests
from datetime import datetime

def main():
    if len(sys.argv) < 2:
        print("Error: No data payload detected.")
        return

    raw_data = sys.argv[1]
    
    try:
        payload = json.loads(raw_data)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        return

    timestamp = payload.get("timestamp", datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    category = payload.get("category", "🚨 GLOBAL MACRO")
    headline = payload.get("headline", "Market shift detected.")
    bias = payload.get("market_bias", "Monitor Focus")

    # 1. Update your GitHub README Dashboard File Table
    new_row = f"| {timestamp} | {category} | {headline} | {bias} |\n"
    readme_path = "README.md"
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        start_anchor = "<!-- ACTIVE_LOGS_START -->"
        if start_anchor in content:
            updated_content = content.replace(start_anchor, f"{start_anchor}\n{new_row}")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            print("Successfully updated GitHub README log.")

    # 2. Hardened Text Log Streaming (Pushes clean tracking rows to text files)
    print("==================================================")
    print(f"🚀 PIPELINE LOGGING METRICS ACTIVE FOR RECORD: {category}")
    print(f"🕒 Timestamp: {timestamp} UTC")
    print(f"📰 Headline: {headline}")
    print(f"📈 Bias: {bias}")
    print("==================================================")

if __name__ == '__main__':
    main()
