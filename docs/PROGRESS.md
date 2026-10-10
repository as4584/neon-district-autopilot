# Progress Ledger

## 2026-10-10: Recovery and Public Showcase

### Verified

- Windows-native regression tests pass without production queues or artwork.
- ACE-Step produced valid 30-second 48 kHz stereo audio.
- 1080p NVENC/AAC rendering produced a valid 30-second preview.
- Local visual QA accepted a relevant cover and rejected an unrelated sleep cover.
- Existing channel videos were organized into two public playlists.
- Unsupported promises about ads, interruptions, and copyright were removed from tracked video descriptions.
- Curated model revisions, download budgets, hashes, and licensing blockers are recorded.
- The initial 50 tests passed on a clean GitHub Actions Windows runner; the expanded 61-test suite passes in both local checkouts.
- Weekly native model staging and sanitized findings tasks are enabled; a live report publication was verified.
- FLUX weights completed SHA256 verification; jazz, sleep bedroom, and cozy rain window generation passed actual inspection and visual QA.
- A deliberately incorrect local jazz cover was rejected for the sleep target.
- Preserved recovery audio passed technical QA: 300 seconds, 48 kHz stereo, -17 dB average and -1 dB peak.
- [Recovery video](https://www.youtube.com/watch?v=glUxXuiUxps) is public, processed successfully, and has a verified 3,601-second duration on the expected channel.
- Future covers are imagery-only; legacy title/logo overlays are not reused. Existing public videos and thumbnails are left untouched.
- Local FFmpeg renders a reusable 30-second camera/light loop, then stream-copies it into long sessions. A real 1080p/30fps preview passed nonblank, motion, duration, and loop-continuity pixel checks.
- A two-loop mux test contains exactly 60 seconds of video and audio and 1,800 video frames.
- Local visual QA retries GPU server failures on the CPU without bypassing its acceptance scores.
- Animated bedroom-frame visual QA passed 10/10/10 using the local CPU fallback after a GPU initialization failure.
- Daily Windows dispatch is enabled at 09:00 local; invoking the dispatcher confirmed it skips an already-published day without another upload.
- The Windows health check passed: seven pending long-form sessions, no generating items, and completed Shorts queue. Eight historical failures remain preserved, not blindly reset.

Tracking: [daily publishing acceptance](https://github.com/as4584/neon-district-autopilot/issues/1), [HeartMuLa auditions](https://github.com/as4584/neon-district-autopilot/issues/2), [Stable Audio gate](https://github.com/as4584/neon-district-autopilot/issues/3).

### Pending Acceptance

- Install and verify isolated alternative music runtimes; audition for vocal leakage and harsh transitions.
- Run balanced challenger trials by series and duration.
- Gather enough equal-age watch-time evidence to retain or replace engines.

### Evidence Rules

No upload is claimed successful merely because a process started. No music-engine winner is declared from lifetime view totals or absent metrics. Public findings expose only aggregates, never credentials, private account data, machine paths, or production logs.
