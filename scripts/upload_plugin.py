"""Upload a release ZIP to the official QGIS plugin repository (plugins.qgis.org) through its XML-RPC API.

    OSGEO_USER=... OSGEO_PASSWORD=... python scripts/upload_plugin.py dist/seranta.3.4.0.zip

Used by .github/workflows/release.yml with repository secrets OSGEO_USER / OSGEO_PASSWORD. The very first version
must be uploaded by hand at https://plugins.qgis.org/plugins/add/ (the plugin then waits for approval by the QGIS team);
every later version can be uploaded with this script.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-2.0-or-later.
"""
import os
import sys
import urllib.parse
import xmlrpc.client

ENDPOINT = "plugins.qgis.org/plugins/RPC2/"


def main(path):
    user, pwd = os.environ.get("OSGEO_USER", ""), os.environ.get("OSGEO_PASSWORD", "")
    if not user or not pwd:
        sys.exit("OSGEO_USER / OSGEO_PASSWORD belum diisi (GitHub: Settings > Secrets and variables > Actions)")
    url = "https://%s:%s@%s" % (urllib.parse.quote(user, safe=""), urllib.parse.quote(pwd, safe=""), ENDPOINT)
    server = xmlrpc.client.ServerProxy(url, verbose=False)
    with open(path, "rb") as fh:
        data = xmlrpc.client.Binary(fh.read())
    try:
        plugin_id, version_id = server.plugin.upload(data)
    except xmlrpc.client.ProtocolError as e:
        sys.exit("Upload ditolak: HTTP %s %s (cek akun OSGeo dan hak upload plugin)" % (e.errcode, e.errmsg))
    except xmlrpc.client.Fault as e:
        sys.exit("Upload ditolak oleh plugins.qgis.org: %s" % e.faultString)
    print("Terunggah: plugin id %s, versi id %s" % (plugin_id, version_id))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
