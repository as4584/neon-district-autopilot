"""Local HF inference worker. Model downloads are a separate, explicit setup step."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="black-forest-labs/FLUX.2-klein-4B")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--check-ready", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.seed < 2**32:
        raise ValueError('Image seed outside supported range')
    try:
        import torch
        from diffusers import Flux2KleinPipeline, ZImagePipeline
        from huggingface_hub import snapshot_download

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        local = Path(__file__).resolve().parents[1] / 'models' / 'flux2-klein-4b'
        snapshot = local if args.model == 'black-forest-labs/FLUX.2-klein-4B' and (local / 'installation.json').is_file() else Path(snapshot_download(args.model, local_files_only=True))
        configuration = json.loads((snapshot / "model_index.json").read_text())
        for component, specification in configuration.items():
            if component.startswith("_") or not isinstance(specification, list):
                continue
            if specification[0] not in ("diffusers", "transformers") or "Tokenizer" in str(specification):
                continue
            folder = snapshot / component
            if "Scheduler" in str(specification):
                continue
            weights = list(folder.glob("*.safetensors"))
            if not weights:
                raise RuntimeError("Cached model weights are incomplete")
            for index in folder.glob("*.safetensors.index.json"):
                shards = set(json.loads(index.read_text())["weight_map"].values())
                if any(not (folder / shard).is_file() for shard in shards):
                    raise RuntimeError("Cached model shards are incomplete")
        if args.check_ready:
            print("Local image runtime and cached CUDA model are ready.")
            return 0
        if not args.prompt_file or not args.output:
            raise RuntimeError("Prompt file and output are required for generation")
        free, _ = torch.cuda.mem_get_info()
        if free < 14 * 1024 ** 3:
            raise RuntimeError("At least 14 GiB of free VRAM is required")
        if args.model == "black-forest-labs/FLUX.2-klein-4B":
            pipeline_class, steps, guidance = Flux2KleinPipeline, 4, 1.0
        elif args.model == "Tongyi-MAI/Z-Image-Turbo":
            pipeline_class, steps, guidance = ZImagePipeline, 9, 0.0
        else:
            raise RuntimeError("Unsupported local image model")
        pipeline = pipeline_class.from_pretrained(
            str(snapshot), torch_dtype=torch.bfloat16, local_files_only=True,
        )
        pipeline.enable_model_cpu_offload()
        image = pipeline(
            prompt=args.prompt_file.read_text(encoding="utf-8"),
            width=1280, height=720, num_inference_steps=steps, guidance_scale=guidance,
            generator=torch.Generator("cuda").manual_seed(args.seed),
        ).images[0]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output)
        return 0
    except Exception as exc:
        print(f"Local image worker failed ({type(exc).__name__}); no cloud fallback.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
