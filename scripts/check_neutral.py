"""Guard for the public edition: fail when a tool text, profile or document names a brand or company.

The list of forbidden names is NOT stored in this public repository. Provide it as a comma-separated list in the
environment variable BRAND_DENYLIST (GitHub: repository secret of the same name), e.g. "name one,name two".

    BRAND_DENYLIST="..." python scripts/check_neutral.py seranta
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.
"""
import os
import re
import sys

EXT = (".py", ".json", ".md", ".txt", ".html", ".qml")


def main(root):
    words = [w.strip() for w in os.environ.get("BRAND_DENYLIST", "").split(",") if w.strip()]
    if not words:
        print("BRAND_DENYLIST kosong: pemeriksaan nama merek dilewati")
        return 0
    rx = re.compile(r"(?<![A-Za-z])(%s)(?![A-Za-z])" % "|".join(re.escape(w) for w in words), re.IGNORECASE)
    bad = 0
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ("__pycache__", ".git")]
        for f in fn:
            if not f.endswith(EXT):
                continue
            p = os.path.join(dp, f)
            with open(p, encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
                    if rx.search(line):
                        bad += 1
                        print("%s:%d: nama merek/perusahaan ditemukan" % (p, i))   # nama tidak dicetak di log publik
    print("Pemeriksaan netral: %d temuan" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "seranta"))
