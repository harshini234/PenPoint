import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "src")]

from penpoint import bulk, data as D, db


class F(io.BytesIO):
    def __init__(self, path):
        super().__init__(Path(path).read_bytes())
        self.name = Path(path).name


def main():
    args = sys.argv[1:] or [ROOT / "demo_data" / n for n in ("cattle.csv", "health_records.csv", "sensehub_alerts.csv")]
    files = [F(a) if a and Path(a).exists() else None for a in args] + [None, None]
    D.ensure_db()
    rep = bulk.import_bundle(files[0], files[1], files[2], replace=True)
    print(f"Database: {db.where_label()}")
    print(f"Imported {rep['lots']} lots, {rep['cattle']} cattle, {rep['events']} health records, {rep['alerts']} SenseHub alerts; as of {rep['as_of']}.")
    for p in rep["problems"]:
        print("  note:", p)


if __name__ == "__main__":
    main()
