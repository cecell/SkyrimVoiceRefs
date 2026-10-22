# Releasing

## One-time setup

- VirusTotal: make a free account at https://www.virustotal.com, copy your API key (profile menu, "API key"), then
  add it to the repository as a secret named `VT_API_KEY`:

      gh secret set VT_API_KEY --repo Cecell/SkyrimVoiceRefs

  (it asks you to paste the key). Without it the build still works, it just skips the VirusTotal step.

## Each release

1. Update `manifest.json` if the voice list changed (Spark repo: `scripts/voice_manifest.py`), commit, push.
2. Tag and push: `git tag v1.0.0 && git push origin v1.0.0`. The "Build release" workflow compiles FFmpeg and the exe,
   tests them, scans them on VirusTotal, attests them and creates a **draft** release with the zip, `SHA256SUMS.txt`
   and notes that already contain the VirusTotal results (also on the run's summary page).
3. If VirusTotal shows detections, submit a false-positive report to each engine that flagged it.
4. Microsoft: https://www.microsoft.com/wdsi/filesubmission, signed in with your Microsoft account. Choose
   **Software developer** and submit the zip from the draft release (it holds `SkyrimVoiceRefs.exe` and
   `ffmpeg\ffmpeg.exe`). If Defender already flags it, pick "Incorrectly detected as malware/malicious". In the notes,
   say it's a new release of your open-source tool and link the GitHub release. Keep the submission ID.
5. Wait for Microsoft's e-mail with the determination ("No malware detected").
6. Edit the draft release notes: fill in the Microsoft result, then **Publish release**.

Every build has new hashes, so steps 3-6 repeat for each release.
