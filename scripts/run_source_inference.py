"""Run source-v2 inference without loading or exposing gold outputs."""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aegislm.environment import load_project_env  # noqa: E402

load_project_env(REPO_ROOT)


def main() -> None:
    from aegislm.artifacts import validate_artifact_path_plan
    from aegislm.inference import (
        SOURCE_MAX_NEW_TOKENS,
        SOURCE_MAX_SEQ_LENGTH,
        make_openai_compatible_source_generator,
        make_static_response_generator,
        make_unsloth_response_generator,
        run_source_inference,
        source_generation_protocol_metadata,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision")
    parser.add_argument("--base-model-id")
    parser.add_argument("--tokenizer-contract-sha256")
    parser.add_argument("--hardware-signature")
    parser.add_argument("--adapter-artifact-sha256")
    parser.add_argument("--adapter-sha256")
    parser.add_argument("--run-role", choices=("base", "adapter"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--backend",
        choices=("unsloth", "openai-compatible", "mock"),
        default="unsloth",
    )
    parser.add_argument(
        "--adapter-path",
        help="Adapter directory for Unsloth; omit to load --model-id as the base.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("raw", "constrained"), default="raw")
    parser.add_argument("--max-seq-length", type=int, default=SOURCE_MAX_SEQ_LENGTH)
    parser.add_argument("--max-new-tokens", type=int, default=SOURCE_MAX_NEW_TOKENS)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--cache-dir", default="models/cache")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--mock-raw-output")
    args = parser.parse_args()
    run_role = args.run_role or ("adapter" if args.adapter_path else "base")
    try:
        generation_protocol = source_generation_protocol_metadata(
            backend=args.backend,
            mode=args.mode,
            max_new_tokens=args.max_new_tokens,
            max_seq_length=args.max_seq_length,
            temperature=args.temperature,
        )
    except ValueError as exc:
        parser.error(str(exc))
    protected_roots = [
        Path(args.cache_dir),
        REPO_ROOT / "data",
        REPO_ROOT / "raw_datasets",
        REPO_ROOT / "models",
        REPO_ROOT / "adapters",
        REPO_ROOT / "checkpoints",
    ]
    if args.adapter_path:
        protected_roots.append(Path(args.adapter_path))
    validate_artifact_path_plan(
        inputs=(args.dataset,),
        outputs=(args.predictions,),
        protected_roots=protected_roots,
        require_new=True,
    )

    if args.backend == "mock":
        if args.mock_raw_output is None:
            parser.error("--mock-raw-output is required for the mock backend")
        generator = make_static_response_generator(args.mock_raw_output)
    elif args.backend == "openai-compatible":
        missing_provenance = [
            flag
            for flag, value in (
                ("--model-revision", args.model_revision),
                ("--tokenizer-contract-sha256", args.tokenizer_contract_sha256),
                ("--hardware-signature", args.hardware_signature),
            )
            if not value
        ]
        if missing_provenance:
            parser.error(
                "openai-compatible comparison requires provenance flags: "
                + ", ".join(missing_provenance)
            )
        if run_role == "adapter" and not args.adapter_artifact_sha256:
            parser.error("adapter runs require --adapter-artifact-sha256")
        if run_role == "adapter" and not args.base_model_id:
            parser.error("adapter runs require --base-model-id")
        generator = make_openai_compatible_source_generator(
            base_url=args.base_url,
            model_id=args.model_id,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            constrained=args.mode == "constrained",
        )
    else:
        if args.mode == "constrained":
            parser.error("constrained mode requires --backend openai-compatible")
        if not args.model_revision:
            parser.error("--model-revision is required for the unsloth backend")
        if args.adapter_path and not args.base_model_id:
            parser.error("adapter runs require --base-model-id")
        generator = make_unsloth_response_generator(
            adapter_path=args.adapter_path,
            max_seq_length=args.max_seq_length,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            cache_dir=args.cache_dir,
            revision=args.model_revision,
            expected_base_model_id=args.base_model_id or args.model_id,
        )

    runtime_provenance = getattr(generator, "aegislm_provenance", {})

    count = run_source_inference(
        dataset_path=args.dataset,
        predictions_path=args.predictions,
        model_id=args.model_id,
        run_id=args.run_id,
        generate_response=generator,
        generation_metadata={
            "backend": args.backend,
            "mode": args.mode,
            "max_new_tokens": args.max_new_tokens,
            "max_seq_length": args.max_seq_length,
            "temperature": args.temperature,
            "requested_model_revision": args.model_revision,
            "base_model_revision": args.model_revision,
            "resolved_model_id": args.base_model_id or args.model_id,
            "tokenizer_contract_sha256": args.tokenizer_contract_sha256,
            "hardware_signature": args.hardware_signature,
            "adapter_path": args.adapter_path,
            "adapter_artifact_sha256": args.adapter_artifact_sha256,
            "adapter_sha256": args.adapter_sha256,
            "run_role": run_role,
            "command": shlex.join([sys.executable, *sys.argv]),
            "packages": _installed_versions(
                ("torch", "transformers", "unsloth", "unsloth-zoo")
            ),
            **generation_protocol,
            **runtime_provenance,
        },
        limit=args.limit,
    )
    print(f"source-v2 inference complete: records={count}, output={args.predictions}")


def _installed_versions(names: tuple[str, ...]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            continue
    return versions


if __name__ == "__main__":
    main()
