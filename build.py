#!/usr/bin/env python3
"""Génère index.html depuis people.json + template.html.
Usage : python3 build.py   (puis publier index.html sur n'importe quel hébergeur statique)
"""
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).parent
data = json.loads((root / "people.json").read_text(encoding="utf-8"))

# contrôles de base : ids uniques, au moins un lien, URLs au bon format
ids = set()
for p in data["people"]:
    assert p["id"] not in ids, f"id en double : {p['id']}"
    ids.add(p["id"])
    assert p["links"], f"aucun lien : {p['id']}"
    assert p["lang"] in ("fr", "en"), f"langue inconnue : {p['id']}"
    for t in p["topics"]:
        assert t in data["meta"]["topics"], f"thème inconnu {t!r} : {p['id']}"
    if "youtube" in p["links"]:
        assert re.fullmatch(r"https://www\.youtube\.com/@[\w.\-]+", p["links"]["youtube"]), p["id"]
    if "github" in p["links"]:
        assert re.fullmatch(r"https://github\.com/[\w.\-]+", p["links"]["github"]), p["id"]

payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = (root / "template.html").read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
(root / "index.html").write_text(html, encoding="utf-8")
print(f"index.html généré : {len(data['people'])} entrées, {len(html)//1024} Ko", file=sys.stderr)
