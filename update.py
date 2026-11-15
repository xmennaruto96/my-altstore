import json, os, urllib.request

REPO = "roothide/Dopamine-roothide"
BUNDLE_ID = "com.opa334.Dopamine-roothide"

req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/releases/latest",
    headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    },
)
rel = json.load(urllib.request.urlopen(req))
ipa = next(a for a in rel["assets"] if a["name"].lower().endswith(".ipa"))

version = rel.get("name") or rel["tag_name"]
date = rel["published_at"]
desc = (rel.get("body") or "").strip()[:500] or "Dopamine with roothide."
icon = "https://raw.githubusercontent.com/opa334/Dopamine/2.x/Application/Dopamine/Assets.xcassets/AppIcon.appiconset/Icon-76%402x.png"

app = {
    "name": "Dopamine (roothide)",
    "bundleIdentifier": BUNDLE_ID,
    "minOSVersion": "15.0",
    "developerName": "roothide",
    "subtitle": "roothide + Dopamine 3",
    "localizedDescription": desc,
    "iconURL": icon,
    "tintColor": "097A73",
    "screenshotURLs": [],
    # legacy fields
    "version": version,
    "versionDate": date,
    "versionDescription": desc,
    "downloadURL": ipa["browser_download_url"],
    "size": ipa["size"],
    # newer format
    "versions": [{
        "version": version,
        "date": date,
        "localizedDescription": desc,
        "downloadURL": ipa["browser_download_url"],
        "size": ipa["size"],
    }],
}

source = {
    "name": "My roothide Source",
    "identifier": "com.example.myroothide",
    "apps": [app],
    "news": [],
}

with open("apps.json", "w") as f:
    json.dump(source, f, indent=2)
