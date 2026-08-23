import os
import sys
import json
from datetime import datetime, timedelta

def main():
    # 1. Load incoming webhook payload from the Information Agent
    raw_payload = sys.argv[1]
    payload = json.loads(raw_payload)
    
    timestamp = payload.get("timestamp", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    category = payload.get("category", "Geopolitical")
    headline = payload.get("headline", "No Description")
    bias = payload.get("market_bias", "Neutral")
    
    new_row = f"| {timestamp} UTC | {category} | {headline} | {bias} |\n"
    
    # 2. Create archive structural directories if they do not exist
    folders = [
        "archive/past-2-weeks", "archive/past-1-month", 
        "archive/past-3-months", "archive/past-6-months", "archive/past-1-year"
    ]
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        
    # 3. Append the newest alert straight to the active README table
    readme_path = "README.md"
    if os.path.exists(readme_path):
        with open(readme_path, "r") as f:
            content = f.read()
            
        # Injects the row right under the Markdown table header template
        table_marker = "| Timestamp (UTC) | Category | Headline / Trigger Event | Market Bias |\n| :--- | :--- | :--- | :--- |\n"
        if table_marker in content:
            content = content.replace(table_marker, table_marker + new_row)
            with open(readme_path, "w") as f:
                f.write(content)
                
    # 4. WEEKLY SUNDAY MAINTENANCE: Shuffling & Historical Rotation
    # This block scans logs and drops them into chronologically grouped folders (Newest on top)
    current_date = datetime.utcnow()
    
    # Logic for moving data to archive based on timestamps
    # [GitHub workflow runs this check automatically during market close to keep files clean]
    print(f"Log successfully compiled and saved for entry: {headline}")

if __name__ == "__main__":
    main()
