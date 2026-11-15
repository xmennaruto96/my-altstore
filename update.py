import json, os, re, urllib.request
from datetime import datetime

# ---- config -------------------------------------------------------------
SOURCE = {
    "name": "My Sideload Source",
    "identifier": "com.example.mysource",   # change to something unique
}
MAX_VERSIONS = 10          # newest N builds kept per app
INCLUDE_PRERELEASES = True # nightly / alpha / beta builds

APPS = [
    {
        "repo": "roothide/Dopamine-roothide",
        "name": "Dopamine (roothide)",
        "bundle_id": "com.opa334.Dopamine-roothide",
        "asset": r"\.ipa$",
        "developer": "roothide",
        "subtitle": "roothide + Dopamine 3",
        "min_os": "15.0",
        "tint": "097A73",
    },
    {
        "repo": "LiveContainer/LiveContainer",
        "name": "LiveContainer",
        "bundle_id": "com.kdt.livecontainer",
        # LiveContainer+SideStore.ipa has the SAME bundle ID, so only one
        # can be listed. Use r"^LiveContainer\+SideStore\.ipa$" to swap.
        "asset": r"^LiveContainer\.ipa$",
        "developer": "LiveContainer",
        "subtitle": "Run iOS apps without installing them",
        "min_os": "15.0",
        "tint": "5B8DEF",
    },
    {
        "repo": "SideStore/SideStore",
        "name": "SideStore",
        "bundle_id": "com.SideStore.SideStore",
        "asset": r"^SideStore\.ipa$",
        "developer": "SideStore Team",
        "subtitle": "Sideloading without a computer",
        "min_os": "15.0",
        "tint": "8E44AD",
    },
    {
        "repo": "rooootdev/lara",
        "name": "lara",
        "bundle_id": "com.roooot.lara",
        "asset": r"\.ipa$",
        "developer": "rooootdev",
        "subtitle": "lara",
        "min_os": "16.0",
        "tint": "E67E22",
    },
]
# -------------------------------------------------------------------------

TOKEN = os.environ.get("GITHUB_TOKEN")


def gh(url):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=h)))


def make_version(rel):
    tag = rel["tag_name"].lstrip("v")
    date = rel["published_at"][:10].replace("-", ".")
    # rolling tags like "nightly"/"alpha" are reused, so make them unique
    if not re.match(r"^\d", tag):
        return f"{date}-{tag}"
    return tag


def build_app(cfg):
    rels = gh(f"https://api.github.com/repos/{cfg['repo']}/releases?per_page=30")
    versions = []
    for rel in rels:
        if rel["draft"] or (rel["prerelease"] and not INCLUDE_PRERELEASES):
            continue
        asset = next((a for a in rel["assets"] if re.search(cfg["asset"], a["name"])), None)
        if not asset:
            continue
        notes = (rel.get("body") or "").strip()[:500] or rel.get("name") or rel["tag_name"]
        versions.append({
            "version": make_version(rel),
            "buildVersion": "1",
            "date": rel["published_at"],
            "localizedDescription": ("[pre-release] " if rel["prerelease"] else "") + notes,
            "downloadURL": asset["browser_download_url"],
            "size": asset["size"],
            "minOSVersion": cfg["min_os"],
        })
    versions.sort(key=lambda v: v["date"], reverse=True)
    versions = versions[:MAX_VERSIONS]
    if not versions:
        return None
    latest = versions[0]
    return {
        "name": cfg["name"],
        "bundleIdentifier": cfg["bundle_id"],
        "developerName": cfg["developer"],
        "subtitle": cfg["subtitle"],
        "localizedDescription": cfg["subtitle"],
        "iconURL": cfg.get("icon", ""),
        "tintColor": cfg["tint"],
        "screenshotURLs": [],
        # legacy fields (latest build)
        "version": latest["version"],
        "versionDate": latest["date"],
        "versionDescription": latest["localizedDescription"],
        "downloadURL": latest["downloadURL"],
        "size": latest["size"],
        # newer format (full history)
        "versions": versions,
    }


apps = []
for cfg in APPS:
    try:
        a = build_app(cfg)
        if a:
            apps.append(a)
        else:
            print(f"no matching assets for {cfg['repo']}")
    except Exception as e:
        print(f"failed {cfg['repo']}: {e}")

with open("apps.json", "w") as f:
    json.dump({**SOURCE, "apps": apps, "news": []}, f, indent=2)
print(f"wrote apps.json with {len(apps)} apps")
