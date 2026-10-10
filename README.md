# Neon District Autopilot

A Windows-native automation case study for [Neon District Archive](https://www.youtube.com/@neondistrictarchive): long instrumental sessions for relaxed listening, organized into **Chill Jazz / Rainy Nights** and **Rest / Sleep**.

This is a clean public showcase, not a copy of the private operating repository. It contains reviewed source, synthetic tests, and sanitized findings. Credentials, production queues, private logs, account backups, media, and model weights are excluded.

## Current Status

| Capability | Evidence / Status |
| --- | --- |
| Local music generation | ACE-Step generated a verified 30-second stereo test on Windows |
| Local artwork replacement | FLUX.2-klein-4B installation in progress; production acceptance pending |
| Visual QA | Local vision model passed a matching cover and rejected a mismatched cover |
| Rendering | Verified 1080p NVENC + AAC test; 1/6/12-hour targets have regression coverage |
| Channel organization | Two public series playlists; existing long-form videos organized |
| Daily publishing | Dispatcher implemented; native task disabled until real recovery upload passes |
| Model experiments | Curated pinned-weight staging and equal-age reporting implemented |
| Alternative music engines | HeartMuLa runtime/auditions pending; Stable Audio license gate pending |
| Automatic model selection | Not enabled; no comparable audience evidence yet |

**This is a work in progress, not a claim of a fully autonomous production deployment.** See [progress](docs/PROGRESS.md) and [findings](findings/experiments.json).

## Workflow

```text
Daily queue -> local instrumental masters -> crossfade mix
           -> local FLUX artwork -> strict visual QA
           -> 1/6/12-hour render -> frame/duration QA
           -> authenticated channel check -> YouTube -> receipt + playlist

Weekly pinned-model staging -> isolated runtime acceptance (pending)
                           -> vocal-free auditions (pending)
                           -> controlled trials (pending)
                           -> equal-age watch-time evidence -> retained model

Weekly analytics -> schema-filtered aggregate findings -> this repository
```

Daily publishing stays on the accepted baseline when challengers are unavailable. Model downloads never execute repository Python code, accept licenses, or enable an unverified engine. Shorts require separate human preview approval.

## Native Schedule

- Daily: 09:00 local time, one long-form dispatch; duplicate protection and queue lock.
- Thursday: 02:00 local time, bounded downloads of reviewed, ungated model revisions.
- Sunday: 17:00 local time, equal-age analytics and sanitized findings publication.

Task installers default to disabled. Tasks require a signed-in Windows user and an available computer. These are native Windows jobs, not paid daily coding-agent runs. There is no cloud uptime guarantee.

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\test.cmd
```

Tests use synthetic fixtures and mocked uploads. Running them does not generate music or upload videos. To operate a channel, configure your own YouTube OAuth credentials, secrets manager, model environments, channel identity checks, and a private queue based on `yt_queue.example.json`. This showcase retains Neon District's channel guard; review it before adapting the code to another channel.

## Costs and Limits

Local inference avoids per-generation Gemini charges. Hardware, electricity, bandwidth, storage, and external service limits still exist. Some downloadable models have commercial restrictions or license gates. Model output is not guaranteed copyright-safe, monetizable, or suitable for sleep; audition and rights checks remain necessary. Long sessions repeat crossfaded generated mixes rather than claiming hours of continuously novel composition.

## Security Boundary

- No credentials, production queues, private Git history, raw logs, or downloaded weights in Git.
- Secrets loaded through Doppler REST into the upload process; image workers receive a stripped, offline environment.
- Strict duration and visual checks before upload; wrong-channel uploads blocked.
- Failed queue items and original masters preserved for diagnosis, not blindly reset.
- Public reporting reconstructs approved fields and stages one findings file only.

Upstream model licenses remain their own. No new license grant is asserted for this showcase source.
