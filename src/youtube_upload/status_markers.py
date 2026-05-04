"""
Classification of YouTube Studio listing-row text.

Studio shows the upload status in a row of `<ytcp-video-row>` (Subiendo /
Procesando / Pendiente / Verificando / etc) and uses different strings in
Spanish vs English. This module exposes a single `classify_row(text)`
function so the polling loop doesn't have to know about i18n strings.

It also exposes the raw marker tables for callers that want to render
status snippets to the user.
"""

from __future__ import annotations

from typing import Literal


# Tokens that mean "something is still happening, do not declare done yet".
IN_PROGRESS_MARKERS: tuple[str, ...] = (
    "subiendo", "uploading",
    "procesando", "processing",
    "pendiente", "pending",
    "verificando", "verificaciones en curso",
    "checking", "checks in progress",
    "cancelar carga", "cancel upload",
)

# Tokens that mean "YouTube aborted the upload, the user must reanudate manually".
INTERRUPTED_MARKERS: tuple[str, ...] = (
    "subida interrumpida",
    "carga interrumpida",
    "upload interrupted",
)

# Tokens that mean "Studio itself crashed, we should retry navigation".
STUDIO_ERROR_MARKERS: tuple[str, ...] = (
    "oops, something went wrong",
    "something went wrong",
    "algo salió mal",
    "algo salio mal",
    "ha ocurrido un error",
    "se produjo un error",
    "intenta volver a cargar",
    "try reloading",
    "try again later",
    "vuelve a intentarlo",
)


RowState = Literal[
    "uploading",
    "processing",
    "checks",
    "pending",
    "interrupted",
    "studio_error",
    "done",
    "empty",
]


def classify_row(row_text: str) -> RowState:
    """
    Return the high-level state for a single Studio video row.

    "empty" means the row text is blank (Studio still loading).
    "done"  means none of the in-progress / interrupted markers matched
            and the text is non-empty — caller still needs two consecutive
            "done" reads before declaring success.
    """
    text = (row_text or "").lower().strip()
    if not text:
        return "empty"

    if any(m in text for m in INTERRUPTED_MARKERS):
        return "interrupted"

    matches = [m for m in IN_PROGRESS_MARKERS if m in text]
    if matches:
        if "subiendo" in matches or "uploading" in matches:
            return "uploading"
        if "procesando" in matches or "processing" in matches:
            return "processing"
        if any(m in matches for m in (
            "verificando", "checking",
            "verificaciones en curso", "checks in progress",
        )):
            return "checks"
        return "pending"

    return "done"


def page_shows_studio_error(page_text: str) -> bool:
    """True when the Studio page itself rendered an error placeholder
    (vs. the upload row showing an in-progress marker)."""
    text = (page_text or "").lower()
    return any(m in text for m in STUDIO_ERROR_MARKERS)
