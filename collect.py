#!/usr/bin/env python3
"""Collecte la veille IA/IT et écrit data/feed.json + data/candidates.json.

Sources : chaînes YouTube (flux RSS), comptes GitHub (flux Atom d'activité),
releases de dépôts, flux de news (RSS/Atom), et découverte de nouveaux créateurs
via les sujets GitHub (claude-skills, agent-skills, claude-code).

Ne stocke que des métadonnées : titre, lien, date, auteur, court extrait.

Usage :
  python3 collect.py                      # collecte réelle (réseau requis)
  python3 collect.py --fixtures DIR --out DIR2   # test hors ligne sur des fichiers d'exemple

Durée attendue sur GitHub Actions (estimation, non mesurée) :
  1er passage : 2 à 3 min (résolution des identifiants de chaînes YouTube en plus)
  passages suivants : 1 à 2 min (~60 requêtes, pause de 0,3 s entre deux)
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent
UA = "veille-ia/1.0 (lecteur de flux personnel)"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

# Verbes de l'activité GitHub que l'on garde ; tout le reste (push, issues, commentaires) est écarté.
GH_RULES = [
    ("created a repository", "Nouveau dépôt"),
    ("made", "Dépôt public"),  # « made <repo> public »
    ("released", "Release"),
    ("published a release", "Release"),
    ("starred", "Étoile"),
]

FIXTURES = None  # dossier d'exemples en mode test


# ---------------------------------------------------------------- utilitaires

def now_utc():
    return datetime.now(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


def fetch(url, headers=None, retries=2, timeout=25):
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Cookie": "CONSENT=YES+1"}
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code in (403, 404, 410):
                break  # inutile de réessayer
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def fixture(name):
    p = FIXTURES / name
    if not p.exists():
        raise FileNotFoundError(f"fixture absente : {name}")
    return p.read_bytes()


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_data(self, d):
        self.out.append(d)


def clean(s, n=240):
    if not s:
        return ""
    try:
        p = _Strip()
        p.feed(s)
        p.close()
        t = "".join(p.out)
    except Exception:
        t = re.sub(r"<[^>]+>", " ", s)
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0] + "…"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def txt(el, path):
    found = el.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def safe_url(u):
    return u if u and re.match(r"^https?://", u) else ""


# ---------------------------------------------------------------- lecture des flux

def parse_feed(data):
    """Retourne une liste de dicts {guid,title,url,date,author,summary} pour du RSS 2.0 ou de l'Atom."""
    root = ET.fromstring(data)
    kind = root.tag.split("}")[-1]
    out = []
    if kind == "feed":
        for e in root.findall("a:entry", NS):
            link = ""
            for l in e.findall("a:link", NS):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            if not link:
                l = e.find("a:link", NS)
                link = l.get("href", "") if l is not None else ""
            out.append({
                "guid": txt(e, "a:id"),
                "title": txt(e, "a:title"),
                "url": link,
                "date": txt(e, "a:published") or txt(e, "a:updated"),
                "author": txt(e, "a:author/a:name"),
                "summary": txt(e, "a:summary") or txt(e, "a:content") or txt(e, "media:group/media:description"),
            })
    else:
        channel = root.find("channel")
        for e in (channel if channel is not None else root).findall("item"):
            out.append({
                "guid": txt(e, "guid"),
                "title": txt(e, "title"),
                "url": txt(e, "link"),
                "date": txt(e, "pubDate") or txt(e, "dc:date"),
                "author": txt(e, "dc:creator"),
                "summary": txt(e, "description") or txt(e, "content:encoded"),
            })
    return out


def classify_github(title):
    t = title.lower()
    for key, label in GH_RULES:
        if key in t:
            if key == "made" and "public" not in t:
                continue
            return label
    return None


# ---------------------------------------------------------------- YouTube : identifiant de chaîne

CHANNEL_PATTERNS = [
    re.compile(r'<link[^>]+type="application/rss\+xml"[^>]+channel_id=(UC[\w-]{22})'),
    re.compile(r'<link[^>]+rel="canonical"[^>]+youtube\.com/channel/(UC[\w-]{22})'),
    re.compile(r'"externalId":"(UC[\w-]{22})"'),
]


def resolve_channel(handle_url, who):
    page = fixture(f"ytpage_{who}.html") if FIXTURES else fetch(handle_url)
    text = page.decode("utf-8", "replace")
    if "consent.youtube.com" in text[:5000]:
        raise RuntimeError("page de consentement YouTube")
    for rx in CHANNEL_PATTERNS:
        m = rx.search(text)
        if m:
            return m.group(1)
    raise RuntimeError("identifiant de chaîne introuvable dans la page")


# ---------------------------------------------------------------- travaux de collecte

def build_jobs(people, sources, defaults):
    jobs = []
    keep = defaults["max_keep_default"]
    for p in people["people"]:
        links = p.get("links", {})
        if links.get("youtube"):
            jobs.append({"id": f"yt:{p['id']}", "name": p["name"], "kind": "youtube", "who": p["id"],
                         "handle_url": links["youtube"], "keep": 30})
        if links.get("github"):
            jobs.append({"id": f"gh:{p['id']}", "name": p["name"], "kind": "github", "who": p["id"],
                         "url": links["github"].rstrip("/") + ".atom", "filter_github": True, "keep": keep})
        for r in p.get("repos", []):
            jobs.append({"id": f"rel:{r}", "name": f"{r} (releases)", "kind": "github", "who": p["id"],
                         "url": f"https://github.com/{r}/releases.atom", "label": "Release", "keep": 20})
    for n in sources.get("news", []):
        jobs.append({"id": n["id"], "name": n["name"], "kind": n["kind"], "url": n["url"],
                     "lang": n.get("lang"), "pending": not n.get("verified"), "keep": n.get("max_keep", keep)})
    for r in sources.get("github_releases", []):
        jobs.append({"id": f"rel:{r['repo']}", "name": r["name"], "kind": "github", "label": "Release",
                     "url": f"https://github.com/{r['repo']}/releases.atom", "pending": not r.get("verified"), "keep": 20})
    return jobs


def run_job(job, channels, now):
    """Retourne (items, dropped). Lève une exception en cas d'échec."""
    if job["kind"] == "youtube":
        cid = channels.get(job["handle_url"])
        if not cid:
            cid = resolve_channel(job["handle_url"], job["who"])
            channels[job["handle_url"]] = cid
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    else:
        url = job["url"]
    data = fixture(f"{safe_name(job['id'])}.xml") if FIXTURES else fetch(url)
    raw = parse_feed(data)
    items, dropped = [], 0
    for r in raw[: max(job["keep"] * 3, 60)]:
        link = safe_url(r["url"])
        title = clean(r["title"], 200)
        if not link or not title:
            dropped += 1
            continue
        label = job.get("label", "")
        if job.get("filter_github"):
            label = classify_github(title)
            if label is None:
                dropped += 1
                continue
        published = parse_date(r["date"]) or now
        key = r["guid"] or link
        item = {
            "id": hashlib.sha1(f"{job['id']}|{key}".encode()).hexdigest()[:16],
            "source": job["id"],
            "name": job["name"],
            "kind": job["kind"],
            "label": label,
            "title": title,
            "url": link,
            "published": iso(published),
        }
        if r["author"] and job["kind"] != "youtube":
            item["author"] = clean(r["author"], 80)
        if job["kind"] in ("news", "papers"):
            s = clean(r["summary"], 220)
            if s:
                item["summary"] = s
        items.append(item)
    items.sort(key=lambda i: i["published"], reverse=True)
    return items[: job["keep"]], dropped


# ---------------------------------------------------------------- découverte de créateurs

def discover(people, settings, previous, token, now):
    cfg = settings["discovery"]
    known = set()
    for p in people["people"]:
        gh = p.get("links", {}).get("github", "")
        if gh:
            known.add(gh.rstrip("/").split("/")[-1].lower())
    ignored = set()
    ig = ROOT / "data" / "ignored.json"
    if ig.exists():
        ignored = {x.lower() for x in json.loads(ig.read_text(encoding="utf-8"))}
    since = (now - timedelta(days=cfg["created_within_days"])).date().isoformat()
    found = {}
    errors = []
    for topic in cfg["topics"]:
        q = f"topic:{topic} created:>{since} stars:>={cfg['min_stars']}"
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": q, "sort": "stars", "order": "desc", "per_page": 30})
        try:
            if FIXTURES:
                data = json.loads(fixture(f"search_{topic}.json"))
            else:
                headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                data = json.loads(fetch(url, headers=headers))
        except Exception as e:  # noqa: BLE001 - on continue avec les autres sujets
            errors.append(f"{topic}: {e}")
            continue
        for r in data.get("items", []):
            owner = r["owner"]["login"]
            if owner.lower() in known or owner.lower() in ignored:
                continue
            cur = found.get(owner.lower())
            if cur is None or r["stargazers_count"] > cur["stars"]:
                found[owner.lower()] = {
                    "login": owner,
                    "url": r["owner"]["html_url"],
                    "type": r["owner"].get("type", "User"),
                    "repo": r["full_name"],
                    "repo_url": r["html_url"],
                    "stars": r["stargazers_count"],
                    "description": clean(r.get("description") or "", 160),
                    "topic": topic,
                }
        if not FIXTURES:
            time.sleep(2.5)  # limite de la recherche GitHub : 30 requêtes/min avec jeton, 10 sans
    prev = {c["login"].lower(): c for c in previous.get("candidates", [])}
    for k, c in found.items():
        c["first_seen"] = prev.get(k, {}).get("first_seen", iso(now))
    ranked = sorted(found.values(), key=lambda c: c["stars"], reverse=True)[: cfg["max_candidates"]]
    return ranked, errors


# ---------------------------------------------------------------- programme principal

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    global FIXTURES
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", help="dossier de fichiers d'exemple (mode test hors ligne)")
    ap.add_argument("--out", default=str(ROOT / "data"), help="dossier de sortie")
    args = ap.parse_args()
    if args.fixtures:
        FIXTURES = Path(args.fixtures)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    people = load_json(ROOT / "people.json", {"people": []})
    sources = load_json(ROOT / "sources.json", {"settings": {}, "news": []})
    settings = sources["settings"]
    now = now_utc()

    prev_feed = load_json(out / "feed.json", {"items": []})
    prev_cands = load_json(out / "candidates.json", {"candidates": []})
    channels = load_json(out / "channels.json", {})

    jobs = build_jobs(people, sources, settings)
    status, collected = [], []
    for job in jobs:
        entry = {"id": job["id"], "name": job["name"], "kind": job["kind"], "pending": bool(job.get("pending")),
                 "checked": iso(now_utc())}
        try:
            items, dropped = run_job(job, channels, now)
            entry.update(ok=True, items=len(items), dropped=dropped)
            collected.extend(items)
        except Exception as e:  # noqa: BLE001 - une source en panne ne bloque pas les autres
            entry.update(ok=False, items=0, error=str(e)[:200])
        status.append(entry)
        if not FIXTURES:
            time.sleep(settings.get("pause_seconds", 0.3))

    # fusion avec l'historique : first_seen conservé, fenêtre de rétention, plafond par source
    prev_by_id = {i["id"]: i for i in prev_feed.get("items", [])}
    merged = dict(prev_by_id)
    for it in collected:
        old = prev_by_id.get(it["id"])
        it["first_seen"] = old["first_seen"] if old and "first_seen" in old else iso(now)
        merged[it["id"]] = it
    cutoff = iso(now - timedelta(days=settings.get("retention_days", 30)))
    items = [i for i in merged.values() if i["published"] >= cutoff]
    keep_by_source = {j["id"]: j["keep"] for j in jobs}
    per_source, final = {}, []
    for i in sorted(items, key=lambda x: x["published"], reverse=True):
        n = per_source.get(i["source"], 0)
        if n < keep_by_source.get(i["source"], settings.get("max_keep_default", 60)):
            per_source[i["source"]] = n + 1
            final.append(i)
    final = final[: settings.get("max_items", 2000)]

    cands, cand_errors = discover(people, settings, prev_cands, os.environ.get("GITHUB_TOKEN"), now)
    if cand_errors and not cands:
        cands = prev_cands.get("candidates", [])  # on garde la liste précédente si la recherche a échoué

    (out / "feed.json").write_text(json.dumps(
        {"generated": iso(now), "retention_days": settings.get("retention_days", 30), "items": final, "sources": status},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "candidates.json").write_text(json.dumps(
        {"generated": iso(now), "errors": cand_errors, "candidates": cands}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "channels.json").write_text(json.dumps(channels, indent=1, sort_keys=True), encoding="utf-8")

    ok = sum(1 for s in status if s["ok"])
    print(f"{ok}/{len(status)} sources OK, {len(final)} éléments, {len(cands)} candidats", file=sys.stderr)
    for s in status:
        if not s["ok"]:
            print(f"  ECHEC {s['id']}: {s.get('error')}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
