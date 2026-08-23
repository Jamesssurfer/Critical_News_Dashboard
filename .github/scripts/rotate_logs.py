import os
import sys
import json
import requests

def main():
    token = os.getenv("NOTION_TOKEN")
    db_id = os.getenv("NOTION_DATABASE_ID")

    print("==================================================")
    print("      NOTION BACKEND CONFIGURATION INTERNALS      ")
    print("==================================================")
    
    if not token or not db_id:
        print("CRITICAL ERROR: Missing secure GitHub vault secrets configurations.")
        return

    # Query the exact database structural layout using the Notion REST API portal
    notion_url = f"https://notion.com{db_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28"
    }

    try:
        response = requests.get(notion_url, headers=headers)
        print(f"Notion Database Connection Status: {response.status_code}")
        
        if response.status_code == 200:
            db_data = response.json()
            print("\n✅ SUCCESS: Linked securely to your spreadsheet grid structure.")
            
            # Map out case-sensitive header naming conventions found by the server
            print("\nDetected Table Properties / Structural Headers:")
            properties = db_data.get("properties", {})
            for prop_name, prop_details in properties.items():
                print(f" -> '{prop_name}' [Type Configuration: {prop_details.get('type')}]")
                
        else:
            print(f"\n❌ REJECTION: Notion rejected your Database ID.")
            print(f"Server Error Log Payload: {response.text}")
            
    except Exception as e:
        print(f"Execution Error: {e}")
    print("==================================================")

if __name__ == '__main__':
    main()
