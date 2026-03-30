import csv
import json
import sys

INPUT_FILE = "quotes.csv"
OUTPUT_FILE = "cleaned_quotes.json"


def main():
    quotes = []

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            quotes.append({
                "old_id": int(row["old_id"]),
                "quote_text": row["quote_text"],
                "author_user_id": row["author_name"] if row["author_name"].isdigit() else None,
                "author_name": row["author_name"] if not row["author_name"].isdigit() else None,
                "added_by_user_id": row["added_by"] if row["added_by"].isdigit() else None,
                "added_by": row["added_by"] if not row["added_by"].isdigit() else None,
                "timestamp": row["timestamp"],
            })

    quotes.sort(key=lambda q: q["old_id"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(quotes, f, indent=2, ensure_ascii=False)

    print("Converted %d quotes to %s" % (len(quotes), OUTPUT_FILE))


if __name__ == "__main__":
    main()
