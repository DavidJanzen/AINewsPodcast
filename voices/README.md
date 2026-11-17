# Voice reference recordings

Voice recordings are not part of the repository (`*.wav`, `*.m4a` and `*.mp3` are git-ignored).

To clone your own voice:

1. Read the text in [`VORLESE_TEXT.txt`](VORLESE_TEXT.txt), or any 10–30 seconds of clear speech, and record it with no background noise.
2. Save the recording as WAV in this folder, e.g. `voices/my_voice.wav`.
3. In `config/default_config.yaml`, set `tts.ref_audio` to the file and `tts.ref_text` to the exact words spoken in it.
