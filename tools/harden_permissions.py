"""Make the Carrier Portal User role read-only on Appointment, Truck and Driver.
Run once from the bench folder, then migrate:

    python3 apps/tos_next/tools/harden_permissions.py apps/tos_next
    bench --site <site> migrate

Safe to run again. It only edits the three DocType JSON files and prints what it changed.
"""
import glob
import json
import sys

ROLE = "Carrier Portal User"
WRITE_KEYS = ("write", "create", "delete", "submit", "cancel", "amend", "import", "email", "print", "share")  # 'share' etc. are not needed by carriers
KEEP = ("read",)


def main(app_root):
    changed = 0
    for name in ("truck", "driver", "appointment"):
        paths = glob.glob(f"{app_root}/**/doctype/{name}/{name}.json", recursive=True)
        if not paths:
            print(f"!! {name}.json not found under {app_root}")
            continue
        for path in paths:
            doc = json.load(open(path))
            touched = False
            for perm in doc.get("permissions", []):
                if perm.get("role") != ROLE:
                    continue
                for k in WRITE_KEYS:
                    if perm.get(k):
                        perm[k] = 0
                        touched = True
                perm["read"] = 1
            if touched:
                json.dump(doc, open(path, "w"), indent=1, ensure_ascii=False)
                open(path, "a").write("\n")
                print(f"changed  {path}")
                changed += 1
            else:
                print(f"already  {path}")
    print(f"{changed} file(s) changed. Now run: bench --site <site> migrate")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
