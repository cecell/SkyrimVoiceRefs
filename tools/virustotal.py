"""Scan release files on VirusTotal and report the results on GitHub (standard library only).

usage: VT_API_KEY=... python tools/virustotal.py <release notes.md> <file> [<file> ...]   (normally via tools/scan_release.py)

Uploads each file (unless VirusTotal already has it), waits for the analyses, then writes a results table to the
GitHub job summary ($GITHUB_STEP_SUMMARY) and into the release notes in place of the "VirusTotal: _(link)_" line.
Never fails the build over a detection: the results are there for people to see. The free public API allows
4 requests a minute, so requests are spaced 16 s apart.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://www.virustotal.com/api/v3"
GUI = "https://www.virustotal.com/gui/file/"
KEY = os.environ.get("VT_API_KEY", "")
_last = [0.0]


def call(method, url, body=None, ctype=None):
    for attempt in range(4):
        wait = 16 - (time.time() - _last[0])  # public API: 4 requests per minute
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url if url.startswith("http") else API + url, data=body, method=method,
                                     headers={"x-apikey": KEY, "accept": "application/json",
                                              **({"content-type": ctype} if ctype else {})})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            detail = e.read()[:300]
            if e.code == 429 and attempt < 3:  # quota busy (per-minute limit or shared use): wait 1, 2, 4 min
                print(f"VirusTotal quota busy, retrying in {60 << attempt} s", flush=True)
                time.sleep(60 << attempt)
                continue
            raise RuntimeError(f"VirusTotal {method} {url}: HTTP {e.code} {detail!r}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(path):
    """-> analysis id. Files over 32 MB go through a one-off upload URL."""
    b = uuid.uuid4().hex
    data = open(path, "rb").read()
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(path)}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode() + data + f"\r\n--{b}--\r\n".encode()
    url = call("GET", "/files/upload_url")["data"] if len(data) > 32 * 2**20 else "/files"
    return call("POST", url, body, f"multipart/form-data; boundary={b}")["data"]["id"]


def wait_for(analysis_id, limit=900):
    t = time.time()
    while time.time() - t < limit:
        a = call("GET", f"/analyses/{analysis_id}")["data"]["attributes"]
        if a.get("status") == "completed":
            return a["stats"], a.get("results", {})
    raise RuntimeError(f"analysis {analysis_id} not finished after {limit} s")


def main(notes, files):
    if not KEY:
        print("VT_API_KEY isn't set; skipping VirusTotal")
        return
    rows, pending = [], []
    for p in files:
        h = sha256(p)
        known = call("GET", f"/files/{h}")
        pending.append((p, h, None if known else upload(p), known))
    for p, h, aid, known in pending:
        if aid:
            stats, results = wait_for(aid)
        else:
            attrs = known["data"]["attributes"]
            stats, results = attrs["last_analysis_stats"], attrs.get("last_analysis_results", {})
        flagged = sorted(f"{e} ({r.get('result')})" for e, r in results.items()
                         if r.get("category") in ("malicious", "suspicious"))
        engines = sum(stats.get(k, 0) for k in ("malicious", "suspicious", "undetected", "harmless"))
        rows.append((os.path.basename(p), stats.get("malicious", 0) + stats.get("suspicious", 0), engines, h, flagged))
    table = ["| File | Flagged by | Report |", "|---|---|---|"]
    for name, bad, engines, h, flagged in rows:
        table.append(f"| `{name}` | {bad} of {engines} engines{': ' + ', '.join(flagged) if flagged else ''} "
                     f"| [VirusTotal]({GUI}{h}) |")
    md = "\n".join(table) + "\n"
    print(md)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### VirusTotal\n\n" + md + "\n")
    if os.path.isfile(notes):
        text = open(notes, encoding="utf-8").read()
        text = text.replace("- VirusTotal: _(link)_\n", "- VirusTotal (scanned during the build):\n\n" + md + "\n")
        open(notes, "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
