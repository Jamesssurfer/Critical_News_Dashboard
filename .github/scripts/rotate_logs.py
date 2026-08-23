import os
import sys
import json
from datetime import datetime, timezone


def main():
    if len(sys.argv) < 2:
        print("Error: No data payload detected.", file=sys.stderr)
        sys.exit(1)

    raw_data = sys.argv[1]

    try:
        payload = json.loads(raw_data)
    except Exception as e:
        print(f"JSON Parsing Error: {e}", file=sys.stderr)
        sys.exit(1)

    timestamp = payload.get(
        "timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    )
    category = payload.get("category", "🚨 GLOBAL MACRO")
    headline = payload.get("headline", "Market shift detected.")
    bias = payload.get("market_bias", "Monitor Focus")

    # NOTE: no trailing \n here — the insertion point below already supplies
    # the single newline needed. Adding one here was what produced a blank
    # line before the next row and broke the markdown table on every run.
    new_row = f"| {timestamp} | {category} | {headline} | {bias} |"

    readme_path = "README.md"
    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_anchor = "<!-- ACTIVE_LOGS_START -->"
    if start_anchor not in content:
        print(f"Error: '{start_anchor}' marker not found in {readme_path}.", file=sys.stderr)
        sys.exit(1)

    # Dedupe guard: skip if this exact row already exists (catches repeat
    # manual workflow_dispatch test runs instead of stacking them).
    if new_row in content:
        print("Duplicate row detected — skipping write.")
        return

    updated_content = content.replace(start_anchor, f"{start_anchor}\n{new_row}", 1)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print("Successfully updated GitHub README log.")
    print("==================================================")
    print(f"Category: {category}")
    print(f"Timestamp: {timestamp} UTC")
    print(f"Headline: {headline}")
    print(f"Bias: {bias}")
    print("==================================================")


if __name__ == "__main__":
    main()
