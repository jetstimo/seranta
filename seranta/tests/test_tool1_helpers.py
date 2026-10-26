# -*- coding: utf-8 -*-
"""Uji regresi fungsi bantu alat 1 (butuh modul qgis; di luar QGIS jalankan dengan stub qgis)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import buat_input_desain as B  # noqa: E402


def test_cluster_label_generic_folder():
    assert B.cluster_label("/x/TES 2", "HPDB_21116433298 3 ILIR RW 004_190HP_RPS.xlsx") == "3 ILIR RW 004"
    assert B.cluster_label("/x/TES 3", "HPDB_JAMBI_21100234687_Perumahan Griya assalam- Extension_101HP_PT.Ekspanindo.xlsx") \
        == "Perumahan Griya assalam- Extension"
    assert B.cluster_label("/x/KANDANG MAS RW 01", "HPDB_BENGKULU_1_X.xlsx") == "KANDANG MAS RW 01"


def test_kode_wilayah():
    assert B.kode_wilayah("/x/TES 1", "HPDB_BANDA ACEH_2356732370_LAMBARO SKEP JL. SYIAH KUALA_607_BMI.xlsx") \
        == "BANDA_ACEH_LAMBARO_SKEP_JL_SYIAH_KUALA"
    assert B.kode_wilayah("/x/MARTOBA RW 002", "HPDB_SIANTAR_1234567890_MARTOBA RW 002_80HP_X.xlsx") == "SIANTAR_MARTOBA_RW_002"


def test_group_fdt_same_code_merged():
    ent = [{"code": "JMB1-MAI01-H04", "x": 103.5691589, "y": -1.666893853, "design": "A", "spl": 7, "prem": 200},
           {"code": "JMB1-MAI01-H04", "x": 103.5689627, "y": -1.66668128, "design": "B", "spl": 4, "prem": 101}]
    import math

    def d(x1, y1, x2, y2):
        return math.hypot((x1 - x2) * 111320 * math.cos(math.radians(y1)), (y1 - y2) * 110574)
    g = B.group_fdt(ent, d)
    assert len(g) == 1 and g[0]["used"] == 11 and g[0]["spread_m"] > 30


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f()
            n += 1
            print("PASS ", k)
    print("%d uji lulus" % n)
