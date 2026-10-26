"""Seranta - release tool (not part of the plugin).
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.

  python scripts/release.py seranta dist [--github USER] [--repo-url URL] [--strict]

  * --github USER  : put https://github.com/USER/seranta into metadata (homepage/tracker/repository)
  * writes integrity.json, validates the official plugins.qgis.org rules,
  * dist/seranta.<version>.zip  -> the file uploaded to https://plugins.qgis.org (by hand the first time,
    afterwards automatically by .github/workflows/release.yml)
  * --repo-url URL : also writes dist/plugins.xml (private repository for Plugin Manager, optional)
  * --strict       : exit 1 on any validation error (used by CI)
"""
import configparser
import datetime
import hashlib
import html
import json
import os
import re
import sys
import zipfile

REQ = ["name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "repository"]


def set_github(src, user):
    base = "https://github.com/%s/seranta" % user
    p = os.path.join(src, "metadata.txt")
    s = open(p, encoding="utf-8").read()
    s = re.sub(r"^homepage=.*$", "homepage=" + base, s, flags=re.M)
    s = re.sub(r"^tracker=.*$", "tracker=" + base + "/issues", s, flags=re.M)
    s = re.sub(r"^repository=.*$", "repository=" + base, s, flags=re.M)
    open(p, "w", encoding="utf-8").write(s)
    p = os.path.join(src, "buat_input_desain.py")
    s = open(p, encoding="utf-8").read()
    s = re.sub(r'^HOMEPAGE = ".*"$', 'HOMEPAGE = "%s"' % base, s, flags=re.M)
    open(p, "w", encoding="utf-8").write(s)


EXCLUDE_DIRS = ("__pycache__", "__MACOSX", "tests")


def files_of(src):
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in EXCLUDE_DIRS)
        for f in sorted(files):
            if f.startswith(".") or f.endswith((".pyc", ".pyo")):
                continue
            yield os.path.join(root, f)


def validate(src, g):
    err, warn = [], []
    for k in REQ:
        if not g.get(k, "").strip():
            err.append("metadata: '%s' kosong" % k)
    for k in ("homepage", "tracker", "repository"):
        v = g.get(k, "")
        if "GITHUB_USER" in v or not v.startswith("https://"):
            err.append("metadata: %s belum diisi URL publik (jalankan dengan --github USER)" % k)
    if "plugin" in g.get("name", "").lower() or "plugin" in os.path.basename(src).lower():
        err.append("nama/folder tidak boleh memuat kata 'plugin'")
    if "%" in open(os.path.join(src, "metadata.txt"), encoding="utf-8").read():
        err.append("metadata.txt memuat tanda %% (rusak saat dibaca configparser)")
    for need in ("LICENSE", "README.md", "__init__.py", "metadata.txt", g.get("icon", "icon.png")):
        if not os.path.exists(os.path.join(src, need)):
            err.append("file wajib tidak ada: %s" % need)
    lic = open(os.path.join(src, "LICENSE"), encoding="utf-8").read() if os.path.exists(os.path.join(src, "LICENSE")) else ""
    if "GNU GENERAL PUBLIC LICENSE" not in lic:
        err.append("LICENSE bukan GPL")
    size = 0
    for p in files_of(src):
        size += os.path.getsize(p)
        ext = os.path.splitext(p)[1].lower()
        if ext in (".exe", ".dll", ".so", ".dylib", ".pyd", ".bin"):
            err.append("binary dilarang: %s" % p)
        if re.match(r"(ui_.*|resources_rc)\.py$", os.path.basename(p)):
            err.append("file hasil generate dilarang: %s" % p)
        if ext == ".py":
            code = open(p, encoding="utf-8").read()
            if re.search(r"\b(urllib|requests|subprocess)\b|\beval\(", code):
                warn.append("cek pemakaian urllib/requests/subprocess/eval di %s" % os.path.basename(p))
            compile(code, p, "exec")
    if size > 20 * 1024 * 1024:
        err.append("paket > 20 MB")
    try:
        tuple(int(x) for x in g["version"].split("."))
    except Exception:
        err.append("version harus angka, mis. 2.0.0")
    if not g.get("changelog", "").startswith(g.get("version", "?")):
        warn.append("changelog sebaiknya diawali versi %s" % g.get("version"))
    return err, warn, size


def main():
    a = sys.argv[1:]
    src, out = a[0], a[1]
    user = a[a.index("--github") + 1] if "--github" in a else ""
    repo_url = a[a.index("--repo-url") + 1].rstrip("/") if "--repo-url" in a else ""
    pid = os.path.basename(os.path.normpath(src))
    if user:
        set_github(src, user)
    fp = {os.path.relpath(p, src).replace(os.sep, "/"): hashlib.sha256(open(p, "rb").read()).hexdigest()
          for p in files_of(src) if p.endswith(".py")}
    c = configparser.ConfigParser()
    c.read(os.path.join(src, "metadata.txt"), encoding="utf-8")
    g = c["general"]
    fp["version"] = g["version"]
    json.dump(fp, open(os.path.join(src, "integrity.json"), "w"), indent=1, sort_keys=True)
    err, warn, size = validate(src, g)
    print("VALIDASI plugins.qgis.org: %d error, %d peringatan, ukuran %.2f MB" % (len(err), len(warn), size / 1e6))
    for e in err:
        print("  ERROR  ", e)
    for w in warn:
        print("  info   ", w)
    os.makedirs(out, exist_ok=True)
    zname = "%s.%s.zip" % (pid, g["version"])
    with zipfile.ZipFile(os.path.join(out, zname), "w", zipfile.ZIP_DEFLATED) as z:
        for p in files_of(src):
            z.write(p, pid + "/" + os.path.relpath(p, src).replace(os.sep, "/"))
    print("ZIP:", os.path.join(out, zname))
    if repo_url:
        open(os.path.join(out, "icon.png"), "wb").write(open(os.path.join(src, g.get("icon", "icon.png")), "rb").read())
        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cdata = lambda k: "<![CDATA[%s]]>" % g.get(k, "")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<plugins>
  <pyqgis_plugin name="%s" version="%s" plugin_id="1">
    <description>%s</description>
    <about>%s</about>
    <version>%s</version>
    <qgis_minimum_version>%s</qgis_minimum_version>
    <qgis_maximum_version>%s</qgis_maximum_version>
    <supports_qt6>True</supports_qt6>
    <homepage>%s</homepage>
    <file_name>%s</file_name>
    <icon>%s/icon.png</icon>
    <author_name>%s</author_name>
    <download_url>%s/%s</download_url>
    <uploaded_by>Seranta</uploaded_by>
    <create_date>2026-10-21T00:00:00</create_date>
    <update_date>%s</update_date>
    <experimental>False</experimental>
    <deprecated>False</deprecated>
    <tags>%s</tags>
    <changelog>%s</changelog>
    <server>False</server>
  </pyqgis_plugin>
</plugins>
""" % (html.escape(g["name"]), g["version"], cdata("description"), cdata("about"), g["version"],
       g["qgisMinimumVersion"], g.get("qgisMaximumVersion", "4.99"), html.escape(g.get("homepage", "")), zname,
       repo_url, html.escape(g["author"]), repo_url, zname, now, cdata("tags"), cdata("changelog"))
        open(os.path.join(out, "plugins.xml"), "w", encoding="utf-8").write(xml)
        for old in os.listdir(out):
            if old.startswith(pid + ".") and old.endswith(".zip") and old != zname:
                os.remove(os.path.join(out, old))
        print("plugins.xml:", os.path.join(out, "plugins.xml"))
    sys.exit(1 if err and (user or "--strict" in a) else 0)


if __name__ == "__main__":
    main()
