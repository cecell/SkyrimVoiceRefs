"""Skyrim Voice References: voice-cloning reference clips for Skyrim's voice types, made from your own copy of
Skyrim Special Edition. Portable: run it from any folder, nothing is installed. The same program runs as the compiled
SkyrimVoiceRefs.exe or as this script with any Python 3.9+ (standard library only):

    SkyrimVoiceRefs.exe                               # every voice type -> .\\voices\\<voice>.wav
    python source\\build_voice_refs.py                 # the same, from the source
    SkyrimVoiceRefs.exe --voices malenord femalenord --out D:\\refs
    SkyrimVoiceRefs.exe --game "D:\\Games\\Skyrim Special Edition"

The game folder is found in the registry (Skyrim's own entry, Steam, GOG); if that fails a dialog asks for it.
For each voice, manifest.json lists the game recordings to use, in order, and exactly which samples of each to keep:
  1. BSA extraction  - read just those recordings (.fuz) out of "Skyrim - Voices_en0.bsa" (nothing else is unpacked)
  2. fuz extraction  - drop the lip-sync block, keeping the xWMA audio (.xwm)
  3. xwm -> wav      - decode with the bundled ffmpeg to 16-bit mono 44.1 kHz
  4. processing      - keep the listed samples of each recording, 10 ms fades at the cut ends
  5. joining         - 300 ms of silence between recordings -> <voice>.wav, checked to the sample against the manifest
  6. cleanup         - the temporary .xwm/.wav files are removed
No game audio ships with this tool.
"""
import argparse
import array
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

COMPILED = "__compiled__" in globals()  # running as the Nuitka-built SkyrimVoiceRefs.exe
HERE = os.path.dirname(os.path.abspath(sys.argv[0] if COMPILED else __file__))
# Release layout: SkyrimVoiceRefs.exe, manifest.json and ffmpeg\ at the top, this script in source\. Files are looked up
# here, then one folder up, so the exe and `python source\build_voice_refs.py` share one manifest and one ffmpeg.
SEARCH = [HERE, os.path.dirname(HERE)]
sys.path.insert(0, HERE)
from skyrim_bsa import Bsa  # noqa: E402


def find_file(*parts):
    for d in SEARCH:
        p = os.path.join(d, *parts)
        if os.path.isfile(p):
            return p
    return None

STEAM_APP = "489830"  # Skyrim Special Edition / Anniversary Edition
GOG_GAME = "1711230643"


# ---- finding the game -----------------------------------------------------------------------------------------------
def _reg(root, key, value):
    try:
        import winreg
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as k:
                    return str(winreg.QueryValueEx(k, value)[0])
            except OSError:
                continue
    except ImportError:
        pass
    return None


def _steam_libraries():
    try:
        import winreg
    except ImportError:
        return []
    steam = _reg(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath") \
        or _reg(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")
    if not steam:
        return []
    libs = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(vdf):
        text = open(vdf, encoding="utf-8", errors="replace").read()
        # each library block: "path" "D:\\SteamLibrary" ... "apps" { "489830" "..." }
        for block in re.split(r'\n\s*"\d+"\s*\n\s*\{', text)[1:]:
            m = re.search(r'"path"\s+"([^"]+)"', block)
            if m and f'"{STEAM_APP}"' in block:
                libs.insert(0, m.group(1).replace("\\\\", "\\"))
            elif m:
                libs.append(m.group(1).replace("\\\\", "\\"))
    return libs


def registry_candidates():
    out = []
    try:
        import winreg
        HKLM = winreg.HKEY_LOCAL_MACHINE
        out.append(_reg(HKLM, r"SOFTWARE\Bethesda Softworks\Skyrim Special Edition", "installed path"))
        out.append(_reg(HKLM, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {STEAM_APP}",
                        "InstallLocation"))
        out.append(_reg(HKLM, rf"SOFTWARE\GOG.com\Games\{GOG_GAME}", "path"))
    except ImportError:
        pass
    out += [os.path.join(lib, "steamapps", "common", "Skyrim Special Edition") for lib in _steam_libraries()]
    return [p for p in out if p]


def data_folder(path):
    """The Data folder for a game folder or a Data folder, if it holds the voice archive; else None."""
    for d in (os.path.join(path, "Data"), path):
        if os.path.isfile(os.path.join(d, ARCHIVE)):
            return d
    return None


def _message(text):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "Skyrim Voice References", 0x40 | 0x40000)  # info icon, topmost


def _pick_folder(title):
    """Windows' own folder picker (shell32 SHBrowseForFolderW), so no GUI toolkit has to be bundled."""
    import ctypes
    from ctypes import wintypes

    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [("hwndOwner", wintypes.HWND), ("pidlRoot", ctypes.c_void_p), ("pszDisplayName", wintypes.LPWSTR),
                    ("lpszTitle", wintypes.LPCWSTR), ("ulFlags", wintypes.UINT), ("lpfn", ctypes.c_void_p),
                    ("lParam", wintypes.LPARAM), ("iImage", ctypes.c_int)]

    shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize(None)
    name = ctypes.create_unicode_buffer(260)
    bi = BROWSEINFOW(None, None, name, title, 0x0001 | 0x0040, None, 0, 0)  # file-system folders, resizable dialog
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return None
    path = ctypes.create_unicode_buffer(1024)
    ok = shell32.SHGetPathFromIDListW(pidl, path)
    ole32.CoTaskMemFree(pidl)
    return path.value if ok else None


def ask_for_game():
    msg = ("Skyrim Special Edition wasn't found automatically.\n\nPick the game's folder (the one with "
           "SkyrimSE.exe) or its Data folder.")
    try:
        while True:
            _message(msg)
            p = _pick_folder("Skyrim Special Edition folder (the one with SkyrimSE.exe)")
            if not p:
                return None
            d = data_folder(p)
            if d:
                return d
            msg = f"\"{ARCHIVE}\" isn't in that folder or its Data folder.\n\nPick the folder with SkyrimSE.exe."
    except (AttributeError, OSError):  # not Windows / no desktop: ask in the console
        print(msg.replace("\n\n", " "))
        p = input("Folder: ").strip().strip('"')
        return data_folder(p) if p else None


def find_data(given):
    if given:
        d = data_folder(given)
        if not d:
            raise SystemExit(f"\"{ARCHIVE}\" isn't in {given} or its Data folder")
        return d
    for p in registry_candidates():
        d = data_folder(p)
        if d:
            return d
    d = ask_for_game()
    if not d:
        raise SystemExit("No game folder given.")
    return d


def find_ffmpeg(given):
    for p in ([given] if given else [find_file("ffmpeg", "ffmpeg.exe"), find_file("ffmpeg.exe"), "ffmpeg"]):
        if p and os.path.isfile(p):
            return os.path.abspath(p)  # Windows can't start a relative path written with "/"
        if p and shutil.which(p):
            return shutil.which(p)
    raise SystemExit("ffmpeg wasn't found; it belongs in the ffmpeg folder next to this program.")


# ---- the six steps --------------------------------------------------------------------------------------------------
def fuz_to_xwm(fuz):
    """A .fuz is "FUZE", version, lip-sync size, then the lip data, then the xWMA audio."""
    magic, _version, lip = struct.unpack_from("<4sII", fuz, 0)
    if magic != b"FUZE":
        raise ValueError("not a .fuz file")
    return fuz[12 + lip:]


def read_pcm(path):
    with wave.open(path) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError(f"{os.path.basename(path)}: expected 16-bit mono audio")
        pcm = array.array("h")
        pcm.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm


def decode(ffmpeg, xwm_path, wav_path, sr):
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", xwm_path, "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
                        wav_path], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError("ffmpeg could not decode " + os.path.basename(xwm_path) + ": " + r.stderr.strip()[:300])
    return read_pcm(wav_path)


def cut(pcm, start, end, fade):
    """Samples start..end of one recording as floats in [-1, 1), faded over `fade` samples at each end that was cut."""
    y = [s / 32768.0 for s in pcm[start:end]]
    if fade > 1:
        for i in range(fade):
            g = i / (fade - 1)
            if start > 0:
                y[i] *= g
            if end < len(pcm):
                y[-1 - i] *= g
    return y


def write_wav(path, samples, sr):
    out = array.array("h", (max(-32768, min(32767, int(round(s * 32767)))) for s in samples))
    if sys.byteorder != "little":
        out.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(out.tobytes())


def build(voice, spec, m, source, out_dir, tmp):
    """source(clip) -> pcm samples of one recording."""
    sr = m["sample_rate"]
    gap, fade = [0.0] * int(m["gap_s"] * sr), int(m["fade_s"] * sr)
    joined = []
    for i, c in enumerate(spec["clips"]):
        pcm = source(c, tmp)
        if len(pcm) != c["source_samples"]:
            raise RuntimeError(f"{os.path.basename(c['path'])}: {len(pcm)} samples, the manifest expects "
                               f"{c['source_samples']} (a mod may replace this line; the original game file is needed)")
        joined += (gap if i else []) + cut(pcm, c["start"], c["end"], fade)
    if len(joined) != spec["samples"]:
        raise RuntimeError(f"built {len(joined)} samples, the manifest expects {spec['samples']}")
    write_wav(os.path.join(out_dir, voice + ".wav"), joined, sr)
    return len(joined) / sr


def from_game(bsa, ffmpeg, sr):
    def source(c, tmp):
        stem = os.path.splitext(os.path.basename(c["path"]))[0]
        xwm_path, wav_path = os.path.join(tmp, stem + ".xwm"), os.path.join(tmp, stem + ".wav")
        with open(xwm_path, "wb") as f:                                     # 1-2. BSA -> .fuz -> .xwm
            f.write(fuz_to_xwm(bsa.read(c["path"])))
        try:
            return decode(ffmpeg, xwm_path, wav_path, sr)                   # 3. .xwm -> .wav
        finally:
            for p in (xwm_path, wav_path):                                  # 6. cleanup as we go
                if os.path.exists(p):
                    os.remove(p)
    return source


def from_wavs(folder):
    """Development: read already-decoded recordings (<folder>/<voice>[_n]/<clip>.wav) instead of the game."""
    dirs = {}
    for top in (folder, os.path.join(folder, "Don'tTrain")):
        if os.path.isdir(top):
            for d in os.listdir(top):
                base, _, n = d.rpartition("_")
                dirs[(base if n.isdigit() else d).lower()] = os.path.join(top, d)

    def source(c, tmp):
        parts = c["path"].split("\\")
        return read_pcm(os.path.join(dirs[parts[3]], os.path.splitext(parts[4])[0] + ".wav"))
    return source


ARCHIVE = "Skyrim - Voices_en0.bsa"


def main():
    ap = argparse.ArgumentParser(description="Make voice-cloning reference clips from Skyrim Special Edition.")
    ap.add_argument("--game", help="the game folder or its Data folder (default: found in the registry, else asked)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(find_file("manifest.json") or HERE), "voices"),
                    help="where the <voice>.wav files go (default: the voices folder beside the program)")
    ap.add_argument("--voices", nargs="*", help="only these voice types (default: all)")
    ap.add_argument("--ffmpeg", help="ffmpeg to use (default: the bundled one)")
    ap.add_argument("--manifest", default=find_file("manifest.json"),
                    help="voice list (default: manifest.json beside the program)")
    ap.add_argument("--from-wavs", help=argparse.SUPPRESS)
    a = ap.parse_args()
    pause = COMPILED and len(sys.argv) == 1  # double-clicked: keep the window open at the end
    try:
        if not a.manifest:
            raise SystemExit("manifest.json wasn't found; it belongs next to the program.")
        m = json.load(open(a.manifest, encoding="utf-8"))
        if m.get("format") != 2:
            raise SystemExit("this manifest needs a newer version of the program")
        global ARCHIVE
        ARCHIVE = m["archive"]
        if a.from_wavs:
            source, where = from_wavs(a.from_wavs), a.from_wavs
        else:
            data = find_data(a.game)
            source, where = from_game(Bsa(os.path.join(data, ARCHIVE)), find_ffmpeg(a.ffmpeg), m["sample_rate"]), data
        voices = a.voices or sorted(m["voices"])
        unknown = [v for v in voices if v not in m["voices"]]
        if unknown:
            raise SystemExit("unknown voice type(s): " + ", ".join(unknown))
        os.makedirs(a.out, exist_ok=True)
        print(f"Reading {ARCHIVE} from {where}\nWriting {len(voices)} references to {a.out}\n")
        tmp = tempfile.mkdtemp(prefix="skyrim_voice_refs_")
        failed = []
        try:
            for v in voices:
                try:
                    secs = build(v, m["voices"][v], m, source, a.out, tmp)
                    print(f"  {v + '.wav':40s} {secs:6.2f} s from {len(m['voices'][v]['clips'])} recording(s)")
                except Exception as e:
                    failed.append(v)
                    print(f"  {v + '.wav':40s} FAILED: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)                          # 6. cleanup
        print(f"\n{len(voices) - len(failed)} of {len(voices)} references written to {a.out}")
        code = 1 if failed else 0
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code if isinstance(e.code, str) else f"Stopped ({e.code})")
        code = 0 if e.code in (None, 0) else 1
    if pause:
        input("\nPress Enter to close.")
    sys.exit(code)


if __name__ == "__main__":
    main()
