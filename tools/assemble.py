"""Lay out the portable release folder, zip it and write SHA256SUMS.txt + draft release notes.

usage: python tools/assemble.py --version 1.0.0 --exe-dir build/build_voice_refs.dist --ffmpeg-dir ffmpeg-out --out dist

dist/SkyrimVoiceRefs/
  SkyrimVoiceRefs.exe (+ the runtime files Nuitka put next to it)
  manifest.json, README.txt, LICENSE.txt
  source/   build_voice_refs.py, skyrim_bsa.py   (python source\\build_voice_refs.py does the same as the exe)
  ffmpeg/   ffmpeg.exe, LICENSE.md, COPYING.LGPLv2.1, SOURCE.txt
"""
import argparse
import hashlib
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "SkyrimVoiceRefs"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--exe-dir", required=True)
    ap.add_argument("--ffmpeg-dir", required=True)
    ap.add_argument("--out", default="dist")
    a = ap.parse_args()
    out = os.path.join(a.out, NAME)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(a.exe_dir, out)
    if not os.path.isfile(os.path.join(out, NAME + ".exe")):
        raise SystemExit(f"{NAME}.exe isn't in {a.exe_dir}")
    shutil.copy2(os.path.join(ROOT, "manifest.json"), out)
    shutil.copy2(os.path.join(ROOT, "README.md"), os.path.join(out, "README.txt"))
    shutil.copy2(os.path.join(ROOT, "LICENSE"), os.path.join(out, "LICENSE.txt"))
    os.makedirs(os.path.join(out, "source"))
    for f in ("build_voice_refs.py", "skyrim_bsa.py"):
        shutil.copy2(os.path.join(ROOT, "src", f), os.path.join(out, "source", f))
    ff = os.path.join(out, "ffmpeg")
    os.makedirs(ff)
    for f in ("ffmpeg.exe", "LICENSE.md", "COPYING.LGPLv2.1"):
        shutil.copy2(os.path.join(a.ffmpeg_dir, f), ff)
    info = open(os.path.join(a.ffmpeg_dir, "build-info.txt"), encoding="utf-8").read()
    repo = os.environ.get("GITHUB_REPOSITORY", "Cecell/SkyrimVoiceRefs")
    run = os.environ.get("GITHUB_RUN_ID")
    with open(os.path.join(ff, "SOURCE.txt"), "w", encoding="utf-8") as f:
        f.write("ffmpeg.exe is FFmpeg, licensed under the GNU Lesser General Public License version 2.1 or later\n"
                "(LICENSE.md, COPYING.LGPLv2.1). It is unmodified FFmpeg source, compiled with only the parts this tool\n"
                "needs, and it is a separate program: SkyrimVoiceRefs.exe only runs it to decode the game's xWMA audio.\n"
                "You may replace it with any other FFmpeg build that can decode xWMA.\n\n"
                + info +
                f"\nBuilt by:       https://github.com/{repo}/blob/main/tools/build_ffmpeg.sh"
                + (f"\nBuild log:      https://github.com/{repo}/actions/runs/{run}" if run else "") + "\n")

    zip_path = shutil.make_archive(os.path.join(a.out, f"{NAME}-{a.version}"), "zip", a.out, NAME)
    files = [zip_path, os.path.join(out, NAME + ".exe"), os.path.join(ff, "ffmpeg.exe")]
    sums = [(sha256(p), os.path.relpath(p, a.out).replace(os.sep, "/")) for p in files]
    with open(os.path.join(a.out, "SHA256SUMS.txt"), "w", encoding="utf-8") as f:
        f.writelines(f"{h}  {p}\n" for h, p in sums)
    with open(os.path.join(a.out, "release-notes.md"), "w", encoding="utf-8") as f:
        f.write(f"Voice-cloning references for 74 Skyrim voice types, built from your own copy of Skyrim SE. "
                f"Made for Chatterbox. Unzip anywhere and run `{NAME}.exe` (or `python source\\build_voice_refs.py`); "
                "see README.txt.\n\n"
                "**No game audio or text is included.**\n\n"
                "### Checks\n"
                "- VirusTotal: _(link)_\n"
                "- Microsoft Security Intelligence (developer submission): _(result)_\n"
                f"- Built by GitHub Actions from this tag, with build provenance: "
                f"`gh attestation verify {NAME}.exe --repo {repo}`\n\n"
                "### SHA-256\n```\n" + "".join(f"{h}  {p}\n" for h, p in sums) + "```\n")
    size = sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(out) for x in fs)
    print(f"{out}: {size / 2**20:.1f} MB; {zip_path}: {os.path.getsize(zip_path) / 2**20:.1f} MB")
    for h, p in sums:
        print(h, p)


if __name__ == "__main__":
    main()
