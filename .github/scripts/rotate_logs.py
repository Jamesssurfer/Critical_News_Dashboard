import os
import sys
import json
from datetime import datetime

def main():
    # 1. Safely extract raw text from command line arguments passed by the workflow
    if len(sys.argv) < 2:
        print("Error: No data payload detected from the action engine.")
        return

    raw_data = sys.argv[1]
    
    # 2. Parse the verified payload string into a valid Python dictionary
    try:
        payload = json.loads(raw_data)
    except Exception as e:
        print(f"Critical Error: Failed to parse structural data packet: {e}")
        print(f"Attempted to read raw data: {raw_data}")
        return

    # Extract macro metrics from the safe dictionary fields
    timestamp = payload.get("timestamp", datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    category = payload.get("category", "🚨 GLOBAL MACRO")
    headline = payload.get("headline", "Unexpected market structural shift detected.")
    bias = payload.get("market_bias", "Monitor Focus")

    # Generate the exact structural row for our Markdown layout
    new_row = f"| {timestamp} | {category} | {headline} | {bias} |\n"
    
    # 3. Inject new row directly below the dashboard target anchor tag
    readme_path = "README.md"
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        start_anchor = "<!-- ACTIVE_LOGS_START -->"
        
        if start_anchor in content:
            # Performs injection directly below the hidden layout indicator anchor
            updated_content = content.replace(start_anchor, f"{start_anchor}\n{new_row}")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
            print(f"Success: Appended new alert for {category} to your dashboard table.")
        else:
            print("Warning: Anchor missing from file text layout. Appending row to bottom.")
            with open(readme_path, "a", encoding="utf-8") as f:
                f.write(f"\n{new_row}")
    else:
        print("Error: README.md file could not be found in root workspace.")

if __name__ == '__main__':
    main()
