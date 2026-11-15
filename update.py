"""Build an AltStore source (apps.json) from GitHub releases.

Version, build number, bundle ID and minimum iOS are read from each IPA's own
Info.plist (via HTTP range requests, so the IPA is not fully downloaded), so
the source can never disagree with the file AltStore downloads.
"""
import io, json, os, plistlib, re, sys, time, urllib.error, urllib.request, zipfile

# ---- config -------------------------------------------------------------
SOURCE = {
    "name": "My Sideload Source",
    "identifier": "com.example.mysource",   # change to something unique
    "subtitle": "Sideloading apps, auto-updated from GitHub",
    "tintColor": "#5E6C84",
    # "iconURL" is added in main() -> icons/generic.png in YOUR repo
}
MAX_VERSIONS = 10           # newest N distinct builds kept per app
INCLUDE_PRERELEASES = True  # nightly / alpha / beta builds

# an app's "icon" is a URL; the SOURCE icon is icons/generic.png from your own repo
APPS = [
    {
        "repo": "roothide/Dopamine-roothide",
        "name": "Dopamine (roothide)",
        "bundle_id": "com.opa334.Dopamine-roothide",
        "asset": r"\.ipa$",
        "developer": "roothide",
        "subtitle": "roothide + Dopamine 3",
        "tint": "#14B290",
        "icon": "https://raw.githubusercontent.com/roothide/Dopamine-roothide/3.x/Application/Dopamine/Assets.xcassets/AppIcon.appiconset/Icon-60%403x.png",
    },
    {
        "repo": "LiveContainer/LiveContainer",
        "name": "LiveContainer",
        "bundle_id": "com.kdt.livecontainer",
        # LiveContainer+SideStore.ipa has the SAME bundle ID, so only one can
        # be listed. Use r"^LiveContainer\+SideStore\.ipa$" to swap.
        "asset": r"^LiveContainer\.ipa$",
        "developer": "LiveContainer",
        "subtitle": "Run iOS apps without installing them",
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
        "tint": "#C013F5",
        "icon": "https://raw.githubusercontent.com/rooootdev/lara/main/lara/other/media.xcassets/AppIcon.appiconset/square.png",
    },
]
# -------------------------------------------------------------------------

TOKEN = os.environ.get("GITHUB_TOKEN")
CACHE_FILE = "cache.json"
BLOCK = 256 * 1024


def http(url, headers=None, tries=3):
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and "api.github.com" in url:
                raise
            last = e
        except Exception as e:
            last = e
        time.sleep(1 + i)
    raise last


def gh(url):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return json.load(http(url, h))


class RangeFile(io.RawIOBase):
    """Read-only seekable file backed by HTTP range requests."""

    def __init__(self, url):
        self.src = url
        self._resolve()
        self.pos = 0
        self.cache = {}

    def _resolve(self):
        r = http(self.src, {"Range": "bytes=0-0"})
        self.url = r.geturl()  # signed CDN URL, avoids a redirect per request
        self.size = int(r.headers["Content-Range"].split("/")[-1])

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _block(self, i):
        if i not in self.cache:
            a, b = i * BLOCK, min((i + 1) * BLOCK, self.size) - 1
            try:
                data = http(self.url, {"Range": f"bytes={a}-{b}"}).read()
            except urllib.error.HTTPError:
                self._resolve()  # signed URL may have expired
                data = http(self.url, {"Range": f"bytes={a}-{b}"}).read()
            self.cache[i] = data
        return self.cache[i]

    def readinto(self, buf):
        n = min(len(buf), max(0, self.size - self.pos))
        out, p = bytearray(), self.pos
        while len(out) < n:
            blk = self._block(p // BLOCK)
            s = p % BLOCK
            take = blk[s:s + (n - len(out))]
            out += take
            p += len(take)
        buf[:n] = out
        self.pos += n
        return n


def read_info(url):
    """Return the key fields of the IPA's main Info.plist."""
    with zipfile.ZipFile(RangeFile(url)) as z:
        names = [n for n in z.namelist() if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)]
        if not names:
            raise RuntimeError("no Info.plist in IPA")
        d = plistlib.loads(z.read(names[0]))
    return {
        "bundle": d["CFBundleIdentifier"],
        "version": str(d["CFBundleShortVersionString"]),
        "build": str(d.get("CFBundleVersion", "1")),
        "minos": str(d.get("MinimumOSVersion", "")),
    }


def is_rolling(rel):
    # tags like "nightly"/"alpha" are re-pointed and re-uploaded in place
    return not re.match(r"^v?\d", rel["tag_name"])


def build_date(rel, asset):
    # a rolling release keeps its ORIGINAL published_at forever, so use the
    # time the asset was actually (re)uploaded
    return asset["updated_at"] if is_rolling(rel) else rel["published_at"]


def generic_icon():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return ""
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/icons/generic.png"


def build_app(cfg, cache):
    rels = gh(f"https://api.github.com/repos/{cfg['repo']}/releases?per_page=30")
    cands = []
    for rel in rels:
        if rel["draft"] or (rel["prerelease"] and not INCLUDE_PRERELEASES):
            continue
        asset = next((a for a in rel["assets"] if re.search(cfg["asset"], a["name"])), None)
        if asset:
            cands.append((build_date(rel, asset), rel, asset))
    cands.sort(key=lambda c: c[0], reverse=True)

    versions, seen = [], set()
    for date, rel, asset in cands:
        if len(versions) >= MAX_VERSIONS:
            break
        key = f"{asset['browser_download_url']}|{asset['size']}|{asset['updated_at']}"
        info = cache.get(key)
        if not info:
            try:
                info = read_info(asset["browser_download_url"])
            except Exception as e:
                print(f"  skip {cfg['repo']} {rel['tag_name']}: cannot read IPA ({e})")
                continue
            cache[key] = info
        if info["bundle"] != cfg["bundle_id"]:
            print(f"  skip {cfg['repo']} {rel['tag_name']}: bundle ID {info['bundle']} != {cfg['bundle_id']}")
            continue
        if info["version"] in seen:  # e.g. "alpha" and "0.7.0-alpha" = same commit
            continue
        seen.add(info["version"])
        notes = (rel.get("body") or "").strip()[:500] or rel.get("name") or rel["tag_name"]
        versions.append({
            "version": info["version"],
            "buildVersion": info["build"],
            "date": date,
            "localizedDescription": ("[pre-release] " if rel["prerelease"] else "") + notes,
            "downloadURL": asset["browser_download_url"],
            "size": asset["size"],
            "minOSVersion": info["minos"] or "15.0",
        })
    if not versions:
        return None
    latest = versions[0]
    icon = generic_icon() if cfg["icon"] == "generic" else cfg["icon"]
    return {
        "name": cfg["name"],
        "bundleIdentifier": cfg["bundle_id"],
        "developerName": cfg["developer"],
        "subtitle": cfg["subtitle"],
        "localizedDescription": cfg["subtitle"],
        "iconURL": icon,
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


def main():
    try:
        cache = json.load(open(CACHE_FILE))
    except Exception:
        cache = {}
    apps = []
    for cfg in APPS:
        print(cfg["repo"])
        try:
            a = build_app(cfg, cache)
        except Exception as e:
            print(f"  failed: {e}")
            continue
        if a:
            apps.append(a)
            print(f"  latest {a['version']}  ({len(a['versions'])} versions)")
        else:
            print("  no usable builds")
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1)
    with open("apps.json", "w") as f:
        src = {**SOURCE}
        if generic_icon():
            src["iconURL"] = generic_icon()
        json.dump({**src, "apps": apps, "news": []}, f, indent=2)
    print(f"wrote apps.json with {len(apps)} apps")
    if len(apps) != len(APPS):
        sys.exit(1)  # make a partial failure visible in Actions


if __name__ == "__main__":
    main()
