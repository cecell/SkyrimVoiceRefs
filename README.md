# Skyrim Voice References

Builds one clean reference recording for each of **74 Skyrim voice types** (MaleNord, FemaleElfHaughty, Serana,
Neloth, ...), made for **[Chatterbox](https://github.com/resemble-ai/chatterbox)** voice-cloning text-to-speech.

The audio comes from **your own copy** of Skyrim Special Edition / Anniversary Edition. This project contains no game
audio and no game text: `manifest.json` only says which voice files to use and which part of each.

## Use

1. Download the latest release zip and unzip it anywhere. Nothing is installed.
2. Double-click `SkyrimVoiceRefs.exe`.
3. The references appear in the `voices` folder next to it: loose files, one per voice type, e.g. `voices\malenord.wav`.

The game folder is found automatically (Skyrim's own registry entry, Steam or GOG). If it isn't, a dialog asks for the
folder that has `SkyrimSE.exe` in it. It takes under a minute and changes nothing in the game folder.

Prefer to run the source? The same program is in `source\`. With any Python 3.9 or newer (no extra packages):

    python source\build_voice_refs.py

Options (both ways):

    --voices malenord femaleelfhaughty    only these voice types
    --out D:\TTS\voices                   write the files somewhere else, e.g. straight into your TTS server's voices folder
    --game "D:\Games\Skyrim Special Edition"   use this game folder instead of searching the registry

## Using the references with Chatterbox

Chatterbox itself has no list of voices: it takes a reference file with every request
(`model.generate(text, audio_prompt_path="voices/malenord.wav")`). Named voices come from the server around it, and the
usual servers use exactly this layout: a folder of loose `.wav` files where **the file name is the voice name**.

So copy the files from `voices` into your server's voices folder (or point `--out` at it). With an OpenAI-compatible
speech server a request then looks like:

    POST /v1/audio/speech   {"model": "chatterbox", "input": "Never should have come here!", "voice": "malenord"}

The file names are the game's voice-type names, so a mod that knows an NPC's voice type (MaleNord, FemaleElfHaughty,
...) can request that voice directly, with no lookup table.

Why the references are built the way they are:

- Chatterbox takes the **speaking style and pacing from the first 6 seconds** of a reference and the **sound of the
  voice from the first 10 seconds**; anything after that only refines its voice fingerprint. So the cleanest, most
  typical line always comes first, and each reference is 12-25 seconds long.
- Every candidate line was measured: background noise, effect filters (ghost, whisper and helmet voices are left out
  because the effect would end up in every cloned line), pitch typical of the voice, and clean starts and ends.
- Lines are trimmed to their speech with 100 ms of their own silence at each end and joined with 300 ms of silence.

Output: 16-bit mono WAV, 44.1 kHz.

## How it works

1. **BSA extraction** - reads only the chosen voice files (`.fuz`) out of `Skyrim - Voices_en0.bsa`.
2. **fuz extraction** - drops the lip-sync data, keeping the xWMA audio.
3. **xWMA to WAV** - decodes with the included ffmpeg.
4. **Processing** - keeps exactly the samples listed in the manifest, with 10 ms fades where a line was cut.
5. **Joining** - puts the lines together; every recording and every result is checked to the sample against the manifest.
6. **Cleanup** - deletes its temporary files.

If a mod replaces one of the chosen lines with a loose file, that doesn't matter: the original archive is read.

## Requirements

- Windows 10 or 11, 64-bit.
- Skyrim Special Edition or Anniversary Edition with **English** voices (`Skyrim - Voices_en0.bsa`). Dawnguard and
  Dragonborn lines are in that archive too.

## Verifying a download

Every release is built by the GitHub Actions workflow in this repository, from the tagged source. The release notes
list the SHA-256 of each file, a VirusTotal link, and the build is attested by GitHub:

    gh attestation verify SkyrimVoiceRefs.exe --repo Cecell/SkyrimVoiceRefs

The exe is not code-signed, so Windows SmartScreen may say "Windows protected your PC" the first time: choose
**More info**, then **Run anyway**. Or run the Python source instead, which you can read first.

## ffmpeg

`ffmpeg\ffmpeg.exe` is [FFmpeg](https://ffmpeg.org), compiled by this repository's workflow from FFmpeg's official
source with only what this tool needs (reading xWMA, decoding WMA v2, resampling, writing WAV). It is licensed under the
GNU LGPL version 2.1 or later; `ffmpeg\LICENSE.txt` has the license and `ffmpeg\SOURCE.txt` the exact source version
and build options. It is a separate program that `SkyrimVoiceRefs.exe` runs; you can replace it with any FFmpeg build
that can decode xWMA.

## A word about trust

If you don't trust my build of ffmpeg.exe I don't blame you at all. My own AV flagged it, quarantined it and told me I
needed to restart to get rid of the horrendous abomination that I had unleashed on it. Here's the address to download
the full release that's 163 MB, it works just as well and the same way:
[ffmpeg-n8.1-latest-win64-lgpl-8.1.zip](https://github.com/BtbN/FFmpeg-Builds/releases/latest) (put its
`bin\ffmpeg.exe` in place of `ffmpeg\ffmpeg.exe`). I was just trying to make a smaller package for everyone but being
helpful gets me in trouble a lot. If you don't trust the FFmpeg build at that address I can't help you anymore, ask
Claude.

If you don't trust this app's exe, I don't blame you for that either. Download Python from
[python.org](https://www.python.org/downloads/windows/) and run the included script directly
(`python source\build_voice_refs.py`). If you don't trust the script, heck, I still don't blame you. Give everything to
Claude, let him tell you what it is and if it's safe. If you don't trust Claude, you're on your own. HFGL.

## License

MIT, see `LICENSE`. This covers this project's code and manifest only. Skyrim, its voice recordings and its text belong
to Bethesda; the voices belong to their performers. Use the references for your own projects, and don't use them to
pass anything off as the actors themselves.
