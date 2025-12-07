import csv

# === ΡΥΘΜΙΣΕΙΣ ===
BASE_URL = "https://soft-skills-project.vercel.app"
INPUT_FILE = "tokens.csv"
OUTPUT_FILE = "quiz_links_out.csv"

# === ΚΕΝΤΡΙΚΗ ΛΟΓΙΚΗ ===
with open(INPUT_FILE, newline='', encoding='utf-8') as f_in, \
     open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f_out:

    reader = csv.DictReader(f_in)
    fieldnames = ["#", "student_id", "token", "pre_test_link", "post_test_link"]
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
    writer.writeheader()

    for i, row in enumerate(reader, start=1):
        token = row.get("token", "").strip()
        sid = row.get("student_id", f"S{i:02d}").strip()
        if not token:
            continue

        pre_link = f"{BASE_URL}/?token={token}&attempt=1"
        post_link = f"{BASE_URL}/?token={token}&attempt=2"

        writer.writerow({
            "#": i,
            "student_id": sid,
            "token": token,
            "pre_test_link": pre_link,
            "post_test_link": post_link
        })

print(f"✅ Έτοιμο! Δημιουργήθηκε το '{OUTPUT_FILE}' με {i} μαθητές.")
