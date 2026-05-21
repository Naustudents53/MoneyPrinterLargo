#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _build_text_generator(provider: str, model: str):
    if not provider and not model:
        return None

    def generate(prompt: str, temperature: float = 0.7) -> str:
        from llm_provider import force_provider, generate_text

        if provider:
            with force_provider(provider, model or None):
                return generate_text(prompt, model_name=model or None, temperature=temperature)
        return generate_text(prompt, model_name=model or None, temperature=temperature)

    return generate


def _disabled_text_generator(_prompt: str, temperature: float = 0.7) -> str:
    raise RuntimeError("LLM disabled by --no-llm")


def build_render_command(
    *,
    channel_id: str,
    script_file: Path,
    duration: int,
    topic: str,
    image_mode: str,
    image_provider: str,
    render_profile: str,
    upload: bool,
    upload_platforms: str,
    llm_provider: str,
    llm_model: str,
    retention_mode: str,
) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT_DIR / "webapp" / "api" / "run_job.py"),
        "generate",
        "--channel-id",
        channel_id,
        "--kind",
        "short",
        "--duration",
        str(duration),
        "--topic",
        topic,
        "--script-file",
        str(script_file),
        "--image-mode",
        image_mode,
    ]
    if image_provider:
        cmd += ["--image-provider", image_provider]
    if render_profile:
        cmd += ["--render-profile", render_profile]
    if upload:
        cmd.append("--upload")
    if upload_platforms:
        cmd += ["--upload-platforms", upload_platforms]
    if llm_provider:
        cmd += ["--llm-provider", llm_provider]
    if llm_model:
        cmd += ["--llm-model", llm_model]
    if retention_mode:
        cmd += ["--retention-mode", retention_mode]
    return cmd


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a persisted long-video script .txt into a 1, 2, or 3 minute "
            "Short narration script."
        )
    )
    parser.add_argument("input", help="Path to the long script .txt file.")
    parser.add_argument(
        "--duration",
        type=int,
        choices=[60, 120, 180],
        default=60,
        help="Target Short duration in seconds: 60, 120, or 180.",
    )
    parser.add_argument("--output", default="", help="Output .txt path. Defaults to .mp/tmp/.")
    parser.add_argument("--topic", default="", help="Override the topic detected in the source file.")
    parser.add_argument("--language", default="espanol", help="Target narration language.")
    parser.add_argument("--llm-provider", default="", help="Optional provider override.")
    parser.add_argument("--llm-model", default="", help="Optional model override.")
    parser.add_argument("--temperature", type=float, default=0.72)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the LLM and use the local extractive fallback.",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Fail instead of writing a local fallback when the LLM call fails.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Also write .mp/tmp/.preview-<id>.txt for the existing generator flow.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Render the final Short through the existing video pipeline. Requires --channel-id.",
    )
    parser.add_argument("--channel-id", default="", help="YouTube channel UUID used when --render is set.")
    parser.add_argument("--image-mode", default="ai", help="Render image mode passed to run_job.py.")
    parser.add_argument(
        "--image-provider",
        default="",
        help="Optional AI image provider for rendering: auto, leonardo, openai, gemini.",
    )
    parser.add_argument(
        "--render-profile",
        choices=["quality", "fast", "turbo"],
        default="",
        help="Optional Short render profile passed to run_job.py.",
    )
    parser.add_argument("--upload", action="store_true", help="Upload after render.")
    parser.add_argument(
        "--upload-platforms",
        default="",
        help="Comma-separated upload targets, for example youtube,tiktok,facebook.",
    )
    parser.add_argument(
        "--retention-mode",
        choices=["standard", "maxima_retencion"],
        default="",
        help="Optional creative mode passed to the Short renderer.",
    )
    parser.add_argument("--print", action="store_true", help="Print the final Short script.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from classes.LongScriptShortener import (
        ShortenOptions,
        shorten_long_script,
        write_short_script_files,
    )

    args = parse_args(argv)
    if args.render and not args.channel_id.strip():
        print("[long-to-short] ERROR: --render requires --channel-id", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    if not input_path.is_file():
        print(f"[long-to-short] ERROR: input file not found: {input_path}", file=sys.stderr)
        return 2

    raw = input_path.read_text(encoding="utf-8", errors="replace")
    options = ShortenOptions(
        duration_seconds=args.duration,
        language=args.language,
        topic=args.topic,
        temperature=args.temperature,
        allow_fallback=not args.no_fallback,
    )
    text_generator = (
        _disabled_text_generator
        if args.no_llm
        else _build_text_generator(args.llm_provider, args.llm_model)
    )

    try:
        result = shorten_long_script(raw, options, text_generator=text_generator)
    except Exception as exc:
        print(f"[long-to-short] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    written = write_short_script_files(
        result,
        output_path=args.output or None,
        preview=args.preview or args.render,
        root_dir=ROOT_DIR,
    )

    mode = "LLM" if result.used_llm else "fallback"
    print(f"[long-to-short] Wrote: {written.output_path}")
    print(
        f"[long-to-short] Target: {result.duration_seconds}s | "
        f"{result.sentence_count}/{result.sentence_target} sentences | "
        f"{result.word_count}/{result.word_target} words | mode={mode}"
    )
    if written.preview_path:
        print(f"[long-to-short] Preview file: {written.preview_path}")
        print(f"PREVIEW_ID={written.preview_id}")
    if args.print:
        print("")
        print(result.script)
    if args.render:
        script_file = written.preview_path
        if script_file is None:
            print("[long-to-short] ERROR: render script file was not created", file=sys.stderr)
            return 1
        cmd = build_render_command(
            channel_id=args.channel_id.strip(),
            script_file=script_file,
            duration=result.duration_seconds,
            topic=result.topic,
            image_mode=args.image_mode,
            image_provider=args.image_provider,
            render_profile=args.render_profile,
            upload=args.upload,
            upload_platforms=args.upload_platforms,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            retention_mode=args.retention_mode,
        )
        print("[long-to-short] Rendering Short with existing pipeline...")
        completed = subprocess.run(cmd, cwd=str(ROOT_DIR))
        return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
