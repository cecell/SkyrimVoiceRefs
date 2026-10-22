# Releasing

1. Update `manifest.json` if the voice list changed (Spark repo: `scripts/voice_manifest.py`), commit, push.
2. Tag and push: `git tag v1.0.0 && git push origin v1.0.0`. The "Build release" workflow compiles FFmpeg and the exe,
   tests them, attests them and creates a **draft** release with the zip, `SHA256SUMS.txt` and notes that already
   link each file's VirusTotal report (by its SHA-256).
3. VirusTotal: download the zip from the draft release and upload it at https://www.virustotal.com (the website; the
   free API's quota is far too small). Upload `SkyrimVoiceRefs.exe` from inside it too. The links in the release notes
   then show the reports.
4. If VirusTotal shows detections, submit a false-positive report to each engine that flagged it.
5. Microsoft: https://www.microsoft.com/wdsi/filesubmission, signed in with your Microsoft account. Choose
   **Software developer** and submit the zip from the draft release (it holds `SkyrimVoiceRefs.exe` and
   `ffmpeg\ffmpeg.exe`). If Defender already flags it, pick "Incorrectly detected as malware/malicious". In the notes,
   say it's a new release of your open-source tool and link the GitHub release. Keep the submission ID.
6. Wait for Microsoft's e-mail with the determination ("No malware detected").
7. Edit the draft release notes: add the Microsoft result, then **Publish release**.

Every build has new hashes, so steps 3-7 repeat for each release.
