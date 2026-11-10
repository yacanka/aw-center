"""Interrupt one named JIRA subtask or one isolated number-confirmation operation for filming."""
import argparse
from contextlib import closing
import sqlite3

from prepare_scene import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("system", choices=["jira", "number"])
    parser.add_argument("state", choices=["hold", "release"])
    args = parser.parse_args()
    generation = prepare(False)
    filename = {"jira": "jira-provider.sqlite3", "number": "numarator.sqlite3"}[args.system]
    with closing(sqlite3.connect(generation / filename, timeout=5)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER IF EXISTS video_response_pause")
        if args.state == "release":
            return
        if args.system == "jira":
            db.execute("""
                CREATE TRIGGER video_response_pause BEFORE INSERT ON issue
                WHEN NEW.parent = 'DEMO-101' AND json_extract(NEW.fields,'$.summary')='Karar listesini doğrula'
                BEGIN SELECT RAISE(ABORT, 'Recording transport interruption'); END
            """)
        else:
            # No other scene assigns numbers concurrently. Limit the interruption to this single number.
            row_id = int(db.execute("SELECT coalesce(max(id),0)+1 FROM numbers").fetchone()[0])
            db.execute(f"""
                CREATE TRIGGER video_response_pause BEFORE UPDATE OF status ON numbers
                WHEN OLD.id = {row_id} AND NEW.status = 'used'
                BEGIN SELECT RAISE(ABORT, 'Recording transport interruption'); END
            """)
            print(f"ATL-KAP-{row_id:04}")


if __name__ == "__main__":
    main()
