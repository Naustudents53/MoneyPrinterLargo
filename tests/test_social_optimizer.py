import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.SocialOptimizer import build_social_plan, choose_caption, ensure_social_plan


def test_social_plan_builds_platform_captions_and_quality_gate():
    plan = build_social_plan(
        video_path="missing.mp4",
        title="El misterio del universo que nadie cuenta",
        description="Una historia corta sobre una senal imposible y su impacto.",
        subject="senal imposible del espacio",
        niche="ciencia y espacio",
        platforms=["youtube", "tiktok", "facebook"],
        existing_titles=[],
    )

    assert plan["trend_injector"]["terms"]
    assert plan["hook_pack"][0]["text"]
    assert plan["first_3_seconds"]["overlay_text"] == plan["hook_pack"][0]["text"]
    assert plan["safe_zone"]["recommended_hook_overlay"]["text"] == plan["hook_pack"][0]["text"]
    assert set(plan["captions"]) == {"youtube", "tiktok", "facebook"}
    assert plan["quality_gate"]["score"] < 100
    assert choose_caption(plan, "tiktok", "fallback") == plan["captions"]["tiktok"]["caption"]


def test_social_plan_detects_recycled_titles():
    plan = build_social_plan(
        video_path="missing.mp4",
        title="La ciudad perdida bajo el desierto",
        description="Un relato documental.",
        existing_titles=["La ciudad perdida bajo el desierto"],
    )

    assert plan["title_recycle"]["status"] == "rewrite_recommended"
    assert plan["title_recycle"]["similarity"] == 1.0
    assert plan["hook_pack"][0]["id"] == "anti_repetido"


def test_ensure_social_plan_persists_sidecar(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not a real mp4")

    plan = ensure_social_plan(
        video_path=str(video),
        title="El archivo secreto de la historia",
        description="Descripcion base para probar captions.",
        platforms=["tiktok"],
    )

    sidecar = video.with_suffix(".meta.json")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["social_plan"]["captions"]["tiktok"]["caption"] == plan["captions"]["tiktok"]["caption"]
