# Local Artwork Direction

Future artwork passes through `yt_art_director.py` before the image worker.
The objective is a coherent, beautiful scene suitable for hours of viewing:
natural light, believable materials, one quiet focal point and visual breathing
room. Nature scenes no longer require artificial neon. Explicit room, jazz and
sleep subjects still control the composition; discovery tags cannot override them.

## How It Works

1. Build a visual brief from the title, music prompt and optional `visual_scene`.
2. Retrieve references for the exact configured image model and scene category.
3. Ask local Ollama for concrete descriptive detail. The agent runs on CPU,
   requests `keep_alive: 0`, uses a bounded output length and makes one request.
4. Generate in the existing isolated image worker. A reproducible seed is derived
   from the item, model and attempt. The worker exits after generation.
5. Evaluate the actual image for scene fit, composition, materials and visible
   defects. A failed review supplies specific feedback to the next prompt and
   changes the seed and framing. Existing bounded retries still apply.

The prompt agent has no tools, cloud provider or download path. Its endpoint is
loopback only. If unavailable or invalid, a recorded `structured_brief` fallback
keeps the pipeline usable. Each cover's JSON records its prompt, seed, image
model, reference IDs and method. A timeout does not prove the Ollama CPU request
has already finished; output is bounded and unloading is requested at completion.

The default visual-quality minimum is now 8/10. The existing `neon_theme_score` JSON field now means fit to the scene's art
direction. It retains its name for report compatibility. Natural scenery can
score highly without neon. Scores are automated screening, not proof of beauty.

## Reference Evidence

`art_reference_library.json` starts with publisher prompting guidance and a
published landscape prompt. These are explicitly labeled; they are not claimed
to be user-approved images or successful local benchmarks. Only the exact model
matches. FLUX, Z-Image Base and Z-Image-Turbo each have separate profiles.
Prompt profiles do not install models or enable unsupported inference runtimes.

Approved local previews become stronger references. Each retains the exact image
hash, prompt, seed and a short note about what worked. Changed, rejected, missing
or cross-model images are excluded. Internet galleries are research sources;
they are never scraped into active instructions during daily publishing.

## Preview and Learn

Create a preview without touching production covers or queues:

```powershell
.\.venv\Scripts\python.exe scripts\preview_art_direction.py --id forest-01 --title "Quiet Forest" --scene "Mossy woodland stream in soft daylight"
```

After reviewing the actual image, retain the lesson:

```powershell
.\.venv\Scripts\python.exe yt_art_director.py --id forest-01 --decision approved --lesson "The open water gives the eye room to rest; irregular moss and subtle light feel believable."
```

Or reject and delete that isolated preview:

```powershell
.\.venv\Scripts\python.exe yt_art_director.py --id forest-01 --decision rejected
```

The small review record remains. Existing source artwork and published videos
are not deleted. Local reviews and images are private and must not be copied to
the public showcase. Local reference approval does not perform a YouTube upload.
