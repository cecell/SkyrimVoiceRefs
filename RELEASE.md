# Releasing

1. Update `manifest.json` if the voice list changed (Spark repo: `scripts/voice_manifest.py`), commit, push.
2. Tag and push: `git tag v1.0.0 && git push origin v1.0.0`. The "Build release" workflow compiles FFmpeg and the exe,
   tests them, attests them and creates a **draft** release with the zip and `SHA256SUMS.txt`.
3. Download the zip from the draft release and unzip it.
4. Microsoft: https://www.microsoft.com/wdsi/filesubmission, signed in with your Microsoft account. Choose
   **Software developer** and submit the zip (it holds `SkyrimVoiceRefs.exe` and `ffmpeg\ffmpeg.exe`). If Defender
   already flags it, pick "Incorrectly detected as malware/malicious". In the notes, say it's a new release of your
   open-source tool and link the GitHub release. Keep the submission ID.
5. VirusTotal: upload the zip at https://www.virustotal.com and copy the report link.
6. Wait for Microsoft's e-mail ("No malware detected" / determination). If any engine on VirusTotal flags the files,
   submit a false-positive report to that vendor too.
7. Edit the draft release notes: paste the VirusTotal link and the Microsoft result, then **Publish release**.

Every build has new hashes, so steps 3-7 repeat for each release.
