import os
import sys
import json
import requests
from datetime import datetime

def push_to_notion(token, database_id, timestamp, category, headline, bias):
    url = "https://notion.com"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    # Rigid block structural mapping for standard text properties
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Headline": {
                "title": [{"text": {"content": f"[{timestamp}] {headline}"}}]
            },
            "Category": {
                "rich_text": [{"text": {"content": str(category)}}]
            },
            "Market Bias": {
                "rich_text": [{"text": {"content": str(bias)}}]
            }
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Notion API Server Status Code Response: {response.status_code}")
    if response.status_code != 200:
        print(f"Notion Server Rejection Details: {response.text}")

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

    # 1. Update GitHub README File Table
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

    # 2. Sync to Notion
    notion_token = os.getenv("NOTION_TOKEN")
    notion_db_id = os.getenv("NOTION_DATABASE_ID")
    if notion_token and notion_db_id:
        push_to_notion(notion_token, notion_db_id, timestamp, category, headline, bias)

if __name__ == '__main__':
    main()
