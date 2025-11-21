# reset_db.py
import argparse, sqlite3, sys, os, shutil, datetime

def backup(db):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = f"{os.path.splitext(db)[0]}.backup-{ts}.db"
    shutil.copyfile(db, dst)
    print(f"[OK] Backup -> {dst}")

def exec_sql(db, sql, params=()):
    con = sqlite3.connect(db)
    cur = con.cursor()
    try:
        if isinstance(sql, (list, tuple)):
            for s in sql:
                cur.execute(s, params if isinstance(params, tuple) else ())
        else:
            cur.execute(sql, params)
        con.commit()
    finally:
        con.close()

def count(db, table):
    con = sqlite3.connect(db)
    cur = con.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]
    finally:
        con.close()

def main():
    p = argparse.ArgumentParser(description="Reset helpers for softskills.db")
    p.add_argument("--db", default="softskills.db", help="path to sqlite db")
    sub = p.add_subparsers(dest="mode", required=True)

    a = sub.add_parser("reset-rater", help="Σβήνει ΜΟΝΟ τις βαθμολογίες ανθρώπου για συγκεκριμένο rater_id")
    a.add_argument("--rater", required=True, help="π.χ. teacher01")

    b = sub.add_parser("reset-human", help="Σβήνει ΟΛΕΣ τις ανθρώπινες βαθμολογίες (humanrating)")

    c = sub.add_parser("reset-all", help="Σβήνει interactions + autorating (full fresh test)")

    args = p.parse_args()

    if not os.path.exists(args.db):
        print(f"[ERR] Δεν βρέθηκε DB: {args.db}")
        sys.exit(1)

    backup(args.db)

    if args.mode == "reset-rater":
        before = count(args.db, "humanrating")
        exec_sql(args.db, "DELETE FROM humanrating WHERE rater_id = ?", (args.rater,))
        after = count(args.db, "humanrating")
        print(f"[OK] humanrating: {before} -> {after} (έσβησες του rater_id={args.rater})")

    elif args.mode == "reset-human":
        before = count(args.db, "humanrating")
        exec_sql(args.db, ["DELETE FROM humanrating", "VACUUM"])
        after = count(args.db, "humanrating")
        print(f"[OK] humanrating: {before} -> {after} (όλες οι ανθρώπινες βαθμολογίες διαγράφηκαν)")

    elif args.mode == "reset-all":
        b1 = count(args.db, "autorating")
        b2 = count(args.db, "interaction")
        exec_sql(args.db, [
            "DELETE FROM autorating",
            "DELETE FROM interaction",
            "VACUUM"
        ])
        a1 = count(args.db, "autorating")
        a2 = count(args.db, "interaction")
        print(f"[OK] autorating: {b1} -> {a1}, interaction: {b2} -> {a2} (full reset)")

if __name__ == "__main__":
    main()
