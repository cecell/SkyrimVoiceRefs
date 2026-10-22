"""Scan a release on VirusTotal from your own PC and put the results in the GitHub release notes.

    $env:VT_API_KEY = "<your key>"
    python tools\\scan_release.py v1.0.0          # the (draft) release: download, scan, update its notes
    python tools\\scan_release.py --run 12345678  # a test build's artifact: download and scan, print the results

Needs the GitHub CLI (gh, signed in) and a free VirusTotal API key. Run it from the repository folder. Uploads the zip,
SkyrimVoiceRefs.exe and ffmpeg\\ffmpeg.exe (a few requests, well inside the public API's 4 a minute / 500 a day).
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import virustotal  # noqa: E402

REPO = "Cecell/SkyrimVoiceRefs"


def gh(*args, capture=True):
    r = subprocess.run(["gh", *args], capture_output=capture, text=True)
    if r.returncode:
        raise SystemExit(f"gh {' '.join(args)} failed: {(r.stderr or '').strip()[:300]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description="Scan a SkyrimVoiceRefs release on VirusTotal")
    ap.add_argument("tag", nargs="?", help="release tag, e.g. v1.0.0 (its notes get the results)")
    ap.add_argument("--run", help="scan a test build's artifact instead (workflow run id); results are only printed")
    a = ap.parse_args()
    if not (a.tag or a.run):
        ap.error("give a release tag or --run <id>")
    if not os.environ.get("VT_API_KEY"):
        raise SystemExit('Set your VirusTotal key first:  $env:VT_API_KEY = "<your key>"')
    tmp = tempfile.mkdtemp(prefix="svr_scan_")
    try:
        if a.run:
            gh("run", "download", a.run, "--repo", REPO, "--dir", tmp)
        else:
            gh("release", "download", a.tag, "--repo", REPO, "--dir", tmp, "--pattern", "*.zip",
               "--pattern", "SHA256SUMS.txt")
        zips = [os.path.join(r, f) for r, _, fs in os.walk(tmp) for f in fs if f.endswith(".zip")]
        if len(zips) != 1:
            raise SystemExit(f"expected one release zip, found {len(zips)}")
        zp = zips[0]
        sums = [os.path.join(r, f) for r, _, fs in os.walk(tmp) for f in fs if f == "SHA256SUMS.txt"]
        if sums:  # the zip must be the one the build published
            want = {line.split()[1]: line.split()[0] for line in open(sums[0], encoding="utf-8") if line.strip()}
            got = hashlib.sha256(open(zp, "rb").read()).hexdigest()
            if want.get(os.path.basename(zp)) != got:
                raise SystemExit("the downloaded zip doesn't match SHA256SUMS.txt")
        out = os.path.join(tmp, "unzipped")
        zipfile.ZipFile(zp).extractall(out)
        files = [zp, os.path.join(out, "SkyrimVoiceRefs", "SkyrimVoiceRefs.exe"),
                 os.path.join(out, "SkyrimVoiceRefs", "ffmpeg", "ffmpeg.exe")]
        notes = os.path.join(tmp, "notes.md")
        if a.tag:
            open(notes, "w", encoding="utf-8").write(gh("release", "view", a.tag, "--repo", REPO,
                                                        "--json", "body", "--jq", ".body"))
        virustotal.main(notes, files)
        if a.tag:
            gh("release", "edit", a.tag, "--repo", REPO, "--notes-file", notes)
            print(f"Release notes of {a.tag} updated with the VirusTotal results.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
