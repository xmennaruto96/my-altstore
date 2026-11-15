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
        "tint": "#14B290",
        "icon": "https://raw.githubusercontent.com/roothide/Dopamine-roothide/3.x/Application/Dopamine/Assets.xcassets/AppIcon.appiconset/Icon-60%403x.png",
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
        "tint": "#0784FC",
        "icon": "https://raw.githubusercontent.com/LiveContainer/LiveContainer/main/screenshots/AppIcon1024.png",
    },
    {
        "repo": "SideStore/SideStore",
        "name": "SideStore",
        "bundle_id": "com.SideStore.SideStore",
        "asset": r"^SideStore\.ipa$",
        "developer": "SideStore Team",
        "subtitle": "Sideloading without a computer",
        "min_os": "15.0",
        "tint": "#BA19F4",
        "icon": "https://raw.githubusercontent.com/SideStore/SideStore/develop/AltStore/Resources/Icons.xcassets/AppIcon.appiconset/1024.png",
    },
    {
        "repo": "rooootdev/lara",
        "name": "lara",
        "bundle_id": "com.roooot.lara",
        "asset": r"\.ipa$",
        "developer": "rooootdev",
        "subtitle": "lara",
        "min_os": "16.0",
        "tint": "#C013F5",
        "icon": "https://raw.githubusercontent.com/rooootdev/lara/main/lara/other/media.xcassets/AppIcon.appiconset/square.png",
    },
]
# -------------------------------------------------------------------------

TOKEN = os.environ.get("GITHUB_TOKEN")


def gh(url):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=h)))


def is_rolling(rel):
    # tags like "nightly" / "alpha" are re-pointed and re-uploaded in place
    return not re.match(r"^v?\d", rel["tag_name"])


def build_date(rel, asset):
    # a rolling release keeps its ORIGINAL published_at forever (e.g. 2023),
    # so use the time the asset was actually (re)uploaded instead
    return asset["updated_at"] if is_rolling(rel) else rel["published_at"]


def make_version(rel, date):
    # prefer the exact build version from the release notes,
    # e.g. "Version: `0.7.0-20261027.1507+cd260851`" (matches the IPA's Info.plist)
    m = re.search(r"Version:\s*`([^`]+)`", rel.get("body") or "")
    if m:
        return m.group(1)
    tag = rel["tag_name"].lstrip("v")
    if is_rolling(rel):
        return f"{date[:10].replace('-', '.')}-{tag}"
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
        date = build_date(rel, asset)
        versions.append({
            "version": make_version(rel, date),
            "buildVersion": "1",
            "date": date,
            "localizedDescription": ("[pre-release] " if rel["prerelease"] else "") + notes,
            "downloadURL": asset["browser_download_url"],
            "size": asset["size"],
            "minOSVersion": cfg["min_os"],
        })
    versions.sort(key=lambda v: v["date"], reverse=True)
    # drop duplicate version strings (e.g. "alpha" and "0.7.0-alpha" can be
    # the same commit); the newest upload wins
    seen, unique = set(), []
    for v in versions:
        if v["version"] not in seen:
            seen.add(v["version"])
            unique.append(v)
    versions = unique[:MAX_VERSIONS]
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
