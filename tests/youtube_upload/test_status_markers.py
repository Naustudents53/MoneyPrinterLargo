"""
Tests for `youtube_upload.status_markers.classify_row`.

Studio uses different strings in Spanish vs English; the classifier
must map them to the same logical state so the polling loop can decide
without caring about locale.
"""

import pytest

from youtube_upload.status_markers import (
    classify_row,
    page_shows_studio_error,
)


@pytest.mark.parametrize("text,expected", [
    # Spanish — uploading
    ("Subiendo 42%", "uploading"),
    ("Cancelar carga", "pending"),
    # English — uploading
    ("Uploading 80%", "uploading"),
    # Spanish — processing
    ("Procesando video", "processing"),
    ("Procesando HD", "processing"),
    # English — processing
    ("Processing 4K", "processing"),
    # Spanish — verification
    ("Verificando", "checks"),
    ("Verificaciones en curso", "checks"),
    # English — verification
    ("Checking content", "checks"),
    ("Checks in progress", "checks"),
    # Pending
    ("Pendiente", "pending"),
    ("Pending", "pending"),
    # Interrupted
    ("Subida interrumpida", "interrupted"),
    ("Carga interrumpida", "interrupted"),
    ("Upload interrupted", "interrupted"),
    # Done — no in-progress markers, has actual content
    ("Mi video genial · Público · 1.2K vistas", "done"),
    ("My awesome video · Public · 5K views", "done"),
    # Empty
    ("", "empty"),
    ("   ", "empty"),
])
def test_classify_row(text, expected):
    assert classify_row(text) == expected


def test_classify_row_case_insensitive():
    assert classify_row("SUBIENDO 50%") == "uploading"
    assert classify_row("PROCESANDO") == "processing"


def test_interrupted_takes_precedence_over_in_progress():
    # If the row text contains an interrupted phrase alongside an
    # in-progress marker, interrupted wins (it's the terminal state).
    assert classify_row("Procesando · Carga interrumpida") == "interrupted"
    assert classify_row("Uploading · Upload interrupted") == "interrupted"


def test_page_shows_studio_error():
    assert page_shows_studio_error("Oops, something went wrong") is True
    assert page_shows_studio_error("Algo salió mal. Intenta volver a cargar") is True
    assert page_shows_studio_error("Ha ocurrido un error en YouTube") is True
    assert page_shows_studio_error("Try reloading") is True
    assert page_shows_studio_error("Vuelve a intentarlo más tarde") is True

    # Negative cases
    assert page_shows_studio_error("Mi video se subió correctamente") is False
    assert page_shows_studio_error("") is False
