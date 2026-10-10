# Model Experiment Policy

## Candidates

| Model | Role | Gate |
| --- | --- | --- |
| ACE-Step | Accepted baseline | Keep daily publishing here during trials |
| HeartMuLa 3B 4-bit | Ungated challenger | Windows runtime and instrumental suitability not yet verified |
| Stable Audio 3 Small-Music | Music-specialized challenger | Human license acceptance and commercial eligibility confirmation |

See [registry](../config/music_models.json). Downloads use immutable revisions, data-only extensions, published weight SHA256 verification, a 20 GiB per-candidate budget, and a 40 GiB free-space reserve. Installing weights does not make an engine production-ready.

## Comparisons

- Compare the first 14 calendar days after public publication, with three days for analytics ingestion.
- Keep jazz and sleep separate; keep 1-, 6-, and 12-hour sessions separate.
- At least three videos and 100 views per arm before review eligibility. These are provisional operational thresholds, not statistical-significance claims.
- Track watch minutes per view, watch hours, generation reliability, and local resource costs.
- Missing or unavailable metrics remain missing. No CTR is fabricated.
- Do not infer a winner from a single low-view upload or longer exposure time.
- A replacement still needs licensed use, reproducible runtime, vocal-free auditions, successful publishing, and comparable audience evidence.

The present implementation stages candidates and reports aggregates. It does **not** yet install arbitrary runtimes, publish challenger trials, or automatically promote engines. Those capabilities remain acceptance-gated work, explicitly tracked rather than implied complete.

Primary sources: [HeartMuLa](https://github.com/HeartMuLa/heartlib), [quantized checkpoint](https://huggingface.co/PavonicAI/HeartMuLa-3B-4bit), [Stable Audio 3](https://github.com/Stability-AI/stable-audio-3), [Stability licensing](https://stability.ai/license).
