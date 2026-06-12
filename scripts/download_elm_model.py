#!/usr/bin/env python3
"""
Download the Phi-3-mini-4k-instruct ONNX model for the ELM engine.

Usage:
    python scripts/download_elm_model.py [--output ./data/models/phi-3-mini]

Requirements:
    pip install huggingface-hub

The model is ~1.7GB (INT4 quantized). It's gitignored and only needed
when ELM_ENABLED=true for local adversarial pipeline role declaration.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Phi-3-mini ONNX model for ELM")
    parser.add_argument(
        "--output",
        type=str,
        default="./data/models/phi-3-mini",
        help="Directory to save the model (default: ./data/models/phi-3-mini)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="microsoft/Phi-3-mini-4k-instruct-onnx",
        help="HuggingFace repo ID",
    )
    parser.add_argument(
        "--subfolder",
        type=str,
        default="cpu_and_mobile/cpu-int4-rtn-block-32",
        help="Subfolder within the repo containing INT4 quantized ONNX files",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface-hub not installed. Run: pip install huggingface-hub")
        sys.exit(1)

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {args.repo} ({args.subfolder}) → {output_path}")
    print("This is ~1.7GB and may take a few minutes...\n")

    try:
        snapshot_download(
            repo_id=args.repo,
            local_dir=str(output_path),
            allow_patterns=[f"{args.subfolder}/*"],
        )
        print(f"\nModel downloaded to {output_path}")
        print("Set ELM_ENABLED=true and ELM_MODEL_PATH={} in .env to use it.".format(
            output_path / args.subfolder
        ))
    except Exception as exc:
        print(f"ERROR: Download failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
