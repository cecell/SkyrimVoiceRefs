# Verbatim copy of bsa.py from the author's skyrimlib library, shipped so this tool needs no extra package.
# Do not edit here: change skyrimlib and copy it again.
"""BSA v104 (zlib) / v105 (lz4 frame) reader plus a layered asset lookup.

Layout mirrors ``skyrim-db-builder/crates/bsa-reader`` and ``probes/bsa_probe.py``:

    header 36 B: "BSA\\0" u32 version u32 folderOffset u32 archiveFlags
                 u32 folderCount u32 fileCount u32 totalFolderNameLen
                 u32 totalFileNameLen u32 contentFlags
    folder record: v104 hash u64 + count u32 + offset u32 (16 B)
                   v105 hash u64 + count u32 + pad u32 + offset u64 (24 B)
    per folder: [u8 len + name NUL] if flags&1, then count x (hash u64, size u32, offset u32)
    file-name block (flags&2): fileCount NUL-terminated names
    data: [u8 len + name] if flags&0x100; compressed -> u32 rawSize + payload.
    compressed = (flags&4) XOR (size & 0x40000000); size &= 0x3FFFFFFF.
    The ONLY v104/v105 difference besides the folder record is the codec: v104 zlib,
    v105 lz4 frame.  The inversion bit and the name prefix behave the same in both.
"""
from __future__ import annotations

import os
import struct
import zlib

FLAG_FOLDER_NAMES = 0x1
FLAG_FILE_NAMES = 0x2
FLAG_COMPRESSED = 0x4
FLAG_EMBED_NAMES = 0x100
SIZE_TOGGLE_COMPRESSION = 0x40000000


class BsaError(ValueError):
    pass


def norm_path(p: str) -> str:
    """Archive/lookup key: lower-case, backslash separators, no leading slash."""
    return p.replace("/", "\\").strip("\\").lower()


class Bsa:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as f:
            hdr = f.read(36)
            if len(hdr) < 36:
                raise BsaError("truncated header")
            magic, version, folder_off, flags, nfold, nfile, _tfn, tfl, _ct = struct.unpack("<4s8I", hdr)
            if magic != b"BSA\0":
                raise BsaError(f"bad magic {magic!r}")
            if version not in (104, 105):
                raise BsaError(f"unsupported BSA version {version}")
            self.version = version
            self.flags = flags
            f.seek(folder_off)
            folders = []
            for _ in range(nfold):
                if version >= 105:
                    raw = f.read(24)
                    if len(raw) < 24:
                        raise BsaError("truncated folder records")
                    _h, cnt, _pad, _off = struct.unpack("<QIIQ", raw)
                else:
                    raw = f.read(16)
                    if len(raw) < 16:
                        raise BsaError("truncated folder records")
                    _h, cnt, _off = struct.unpack("<QII", raw)
                folders.append(cnt)
            recs = []
            for cnt in folders:
                fname = ""
                if flags & FLAG_FOLDER_NAMES:
                    nb = f.read(1)
                    name = f.read(nb[0]) if nb else b""
                    if not nb or len(name) != nb[0]:
                        raise BsaError("truncated folder name")
                    fname = name.rstrip(b"\0").decode("latin-1")
                for _ in range(cnt):
                    raw = f.read(16)
                    if len(raw) < 16:
                        raise BsaError("truncated file records")
                    fh, size, off = struct.unpack("<QII", raw)
                    recs.append((fname, fh, size, off))
            if len(recs) != nfile:
                raise BsaError(f"folder records list {len(recs)} files, header says {nfile}")
            names: list[bytes] = []
            if flags & FLAG_FILE_NAMES:
                blob = f.read(tfl)
                names = blob.split(b"\0")[:nfile]
                held = blob.count(b"\0")
                if len(blob) != tfl or held < nfile:
                    raise BsaError(f"file-name block holds {held} names, header says {nfile}")
        self._entries: dict[str, tuple[int, int, bool]] = {}
        default_comp = bool(flags & FLAG_COMPRESSED)
        for i, (fname, fh, size, off) in enumerate(recs):
            nm = names[i].decode("latin-1") if i < len(names) else f"{fh:016x}"
            comp = default_comp ^ bool(size & SIZE_TOGGLE_COMPRESSION)
            size &= 0x3FFFFFFF
            key = norm_path(fname + "\\" + nm) if fname else norm_path(nm)
            self._entries[key] = (off, size, comp)

    def names(self) -> list[str]:
        return sorted(self._entries)

    def __contains__(self, path: str) -> bool:
        return norm_path(path) in self._entries

    def read(self, path: str) -> bytes:
        key = norm_path(path)
        try:
            off, size, comp = self._entries[key]
        except KeyError:
            raise KeyError(f"{path!r} not in {self.path}") from None
        with open(self.path, "rb") as f:
            f.seek(off)
            if self.flags & FLAG_EMBED_NAMES:
                # v104/v105: a bstring (u8 length, no NUL) of the full path precedes the
                # data and counts toward the record size.  None of the four archives the
                # tests read sets this flag (Meshes0 0x87, RaceMenu 0x1f, ECE 0x97).
                nb = f.read(1)
                if not nb:
                    raise BsaError(f"{path!r}: truncated entry")
                f.read(nb[0])
                size -= 1 + nb[0]
            data = f.read(size) if size >= 0 else b""
        if size < 0 or len(data) != size:
            raise BsaError(f"{path!r}: truncated entry")
        if not comp:
            return data
        if size < 4:
            raise BsaError(f"{path!r}: compressed entry has no size prefix")
        (raw_len,) = struct.unpack("<I", data[:4])
        payload = data[4:]
        if self.version >= 105:
            import lz4.frame
            out = lz4.frame.decompress(payload)
        else:
            out = zlib.decompress(payload)
        if len(out) != raw_len:
            raise BsaError(f"{path!r}: inflated {len(out)} bytes, header says {raw_len}")
        return out


class AssetStack:
    """Ordered layers (loose directories and BSAs); the first layer holding a path wins.

    Paths are relative to the data root (``meshes/actors/...``), any slash style,
    any case.  Real-data tests build one stack per scenario so nothing ever reads
    the Vortex-deployed game ``Data`` folder.
    """

    def __init__(self):
        self._layers: list[tuple[str, object]] = []

    def add_dir(self, root: str) -> "AssetStack":
        self._layers.append(("dir", root))
        return self

    def add_bsa(self, path: str) -> "AssetStack":
        self._layers.append(("bsa", Bsa(path)))
        return self

    def _find_loose(self, root: str, rel: str) -> str | None:
        p = os.path.join(root, *rel.replace("\\", "/").split("/"))
        if os.path.isfile(p):
            return p
        # case-insensitive fallback for case-sensitive filesystems
        cur = root
        for part in rel.replace("\\", "/").split("/"):
            try:
                match = next(e for e in os.listdir(cur) if e.lower() == part.lower())
            except (StopIteration, FileNotFoundError, NotADirectoryError):
                return None
            cur = os.path.join(cur, match)
        return cur if os.path.isfile(cur) else None

    def exists(self, rel: str) -> bool:
        return self.locate(rel) is not None

    def locate(self, rel: str):
        for kind, obj in self._layers:
            if kind == "dir":
                p = self._find_loose(obj, rel)
                if p:
                    return ("dir", p)
            elif rel in obj:
                return ("bsa", obj)
        return None

    def read(self, rel: str) -> bytes:
        hit = self.locate(rel)
        if hit is None:
            raise FileNotFoundError(rel)
        kind, obj = hit
        if kind == "dir":
            with open(obj, "rb") as f:
                return f.read()
        return obj.read(rel)
