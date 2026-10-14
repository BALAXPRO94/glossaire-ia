#!/usr/bin/env python3
"""Test hors ligne du collecteur sur des flux d'exemple (formats YouTube, GitHub, RSS, Atom).
Usage : python3 tests/test_collect.py     Durée : moins de 2 s.
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
now = datetime.now(timezone.utc)


def d(days_ago, hour=10):
    t = (now - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return t


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def rfc(t):
    return t.strftime("%a, %d %b %Y %H:%M:%S +0000")


YT = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <link rel="self" href="http://www.youtube.com/feeds/videos.xml?channel_id=UCaaaaaaaaaaaaaaaaaaaaaa"/>
 <id>yt:channel:aaaaaaaaaaaaaaaaaaaaaa</id><title>Chaîne exemple</title>
 <author><name>Chaîne exemple</name></author>
 <entry><id>yt:video:V1</id><yt:videoId>V1</yt:videoId><title>Exemple &amp; vidéo récente</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=V1"/><author><name>Chaîne exemple</name></author>
  <published>{iso(d(1))}</published><updated>{iso(d(1))}</updated>
  <media:group><media:description>Description longue de la vidéo.</media:description></media:group></entry>
 <entry><id>yt:video:V2</id><yt:videoId>V2</yt:videoId><title>Exemple vidéo ancienne</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=V2"/><author><name>Chaîne exemple</name></author>
  <published>{iso(d(60))}</published><updated>{iso(d(60))}</updated></entry>
</feed>"""

YT_PAGE = ('<html><head><link rel="alternate" type="application/rss+xml" title="RSS" '
           'href="https://www.youtube.com/feeds/videos.xml?channel_id=UCaaaaaaaaaaaaaaaaaaaaaa"></head></html>')

GH = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
 <id>tag:github.com,2008:/exemple</id><title>exemple's Activity</title>
 <entry><id>tag:github.com,2008:CreateEvent/1</id><published>{iso(d(1))}</published>
  <link type="text/html" rel="alternate" href="https://github.com/exemple/nouvel-outil"/>
  <title type="html">exemple created a repository exemple/nouvel-outil</title><author><name>exemple</name></author></entry>
 <entry><id>tag:github.com,2008:PushEvent/2</id><published>{iso(d(1, 12))}</published>
  <link type="text/html" rel="alternate" href="https://github.com/exemple/x/compare/a...b"/>
  <title type="html">exemple pushed to main in exemple/x</title><author><name>exemple</name></author></entry>
 <entry><id>tag:github.com,2008:WatchEvent/3</id><published>{iso(d(2))}</published>
  <link type="text/html" rel="alternate" href="https://github.com/autre/projet"/>
  <title type="html">exemple starred autre/projet</title><author><name>exemple</name></author></entry>
 <entry><id>tag:github.com,2008:PublicEvent/4</id><published>{iso(d(3))}</published>
  <link type="text/html" rel="alternate" href="https://github.com/exemple/prive-devenu-public"/>
  <title type="html">exemple made exemple/prive-devenu-public public</title><author><name>exemple</name></author></entry>
</feed>"""

RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
 <channel><title>arXiv exemple</title><link>https://arxiv.org/</link>
  <item><title>Un article exemple</title><link>https://arxiv.org/abs/0000.00001</link>
   <description>&lt;p&gt;Résumé avec &lt;b&gt;HTML&lt;/b&gt; et entités &amp;amp; autres.&lt;/p&gt;</description>
   <guid isPermaLink="false">oai:arXiv.org:0000.00001</guid><pubDate>{rfc(d(0, 2))}</pubDate><dc:creator>A. Auteur</dc:creator></item>
  <item><title>Sans lien</title><description>x</description><pubDate>{rfc(d(0, 3))}</pubDate></item>
 </channel></rss>"""

ATOM_BLOG = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog exemple</title><id>x</id>
 <entry><title>Billet exemple</title><link href="https://blog.example/billet" rel="alternate"/>
  <id>https://blog.example/billet</id><updated>{iso(d(0, 4))}</updated>
  <summary type="html">&lt;p&gt;Court extrait du billet.&lt;/p&gt;</summary></entry>
</feed>"""

SEARCH = json.dumps({"items": [
    {"full_name": "nouveau/skills-top", "html_url": "https://github.com/nouveau/skills-top", "stargazers_count": 340,
     "description": "Une collection de skills", "owner": {"login": "nouveau", "html_url": "https://github.com/nouveau", "type": "User"}},
    {"full_name": "cole/connu", "html_url": "https://github.com/coleam00/connu", "stargazers_count": 999,
     "description": "déjà dans le glossaire", "owner": {"login": "coleam00", "html_url": "https://github.com/coleam00", "type": "User"}},
]})


def run(fx, out):
    r = subprocess.run([sys.executable, str(ROOT / "collect.py"), "--fixtures", str(fx), "--out", str(out)],
                       capture_output=True, text=True)
    return r


def main():
    with tempfile.TemporaryDirectory() as tmp:
        fx, out = Path(tmp) / "fx", Path(tmp) / "out"
        fx.mkdir()
        (fx / "yt_cole-medin.xml").write_text(YT, encoding="utf-8")
        (fx / "ytpage_cole-medin.html").write_text(YT_PAGE, encoding="utf-8")
        (fx / "gh_simon-willison.xml").write_text(GH, encoding="utf-8")
        (fx / "arxiv-cs-ai.xml").write_text(RSS, encoding="utf-8")
        (fx / "simon-willison-blog.xml").write_text(ATOM_BLOG, encoding="utf-8")
        (fx / "korben.xml").write_text("<rss><channel><item>pas du xml valide", encoding="utf-8")  # doit échouer proprement
        (fx / "search_claude-skills.json").write_text(SEARCH, encoding="utf-8")

        r = run(fx, out)
        assert r.returncode == 0, r.stderr
        feed = json.loads((out / "feed.json").read_text(encoding="utf-8"))
        items = {i["source"] + "|" + i["title"]: i for i in feed["items"]}

        # YouTube : titre décodé, vidéo de 60 jours hors fenêtre de 30 jours, identifiant de chaîne mis en cache
        assert "yt:cole-medin|Exemple & vidéo récente" in items, items.keys()
        assert not any("ancienne" in k for k in items), "la vidéo de 60 jours doit être écartée"
        assert json.loads((out / "channels.json").read_text())["https://www.youtube.com/@ColeMedin"] == "UCaaaaaaaaaaaaaaaaaaaaaa"

        # GitHub : on garde création, passage en public, étoile ; on écarte les push
        labels = sorted(i["label"] for i in feed["items"] if i["source"] == "gh:simon-willison")
        assert labels == ["Dépôt public", "Nouveau dépôt", "Étoile"], labels
        st = {s["id"]: s for s in feed["sources"]}
        assert st["gh:simon-willison"]["dropped"] == 1

        # RSS : HTML retiré, entrée sans lien écartée ; Atom : extrait propre
        arx = [i for i in feed["items"] if i["source"] == "arxiv-cs-ai"]
        assert len(arx) == 1 and arx[0]["summary"] == "Résumé avec HTML et entités & autres.", arx
        assert arx[0]["author"] == "A. Auteur"
        blog = [i for i in feed["items"] if i["source"] == "simon-willison-blog"]
        assert blog and blog[0]["summary"] == "Court extrait du billet."

        # Une source en panne est signalée sans bloquer les autres
        assert st["korben"]["ok"] is False and st["korben"]["error"]
        assert st["arxiv-cs-ai"]["ok"] is True

        # Découverte : le nouveau créateur apparaît, celui déjà au glossaire (coleam00) est exclu
        cands = json.loads((out / "candidates.json").read_text(encoding="utf-8"))["candidates"]
        assert [c["login"] for c in cands] == ["nouveau"], cands

        # Second passage : first_seen conservé, pas de doublons
        first = {i["id"]: i["first_seen"] for i in feed["items"]}
        r2 = run(fx, out)
        assert r2.returncode == 0, r2.stderr
        feed2 = json.loads((out / "feed.json").read_text(encoding="utf-8"))
        assert len(feed2["items"]) == len(feed["items"]), "doublons après second passage"
        assert all(first[i["id"]] == i["first_seen"] for i in feed2["items"]), "first_seen modifié"

        # Aucun fichier : toutes les sources échouent -> code de sortie 1
        empty = Path(tmp) / "vide"
        empty.mkdir()
        r3 = run(empty, Path(tmp) / "out3")
        assert r3.returncode == 1, "code 1 attendu quand aucune source ne répond"

    print("OK : tous les tests passent")


if __name__ == "__main__":
    main()
