"""Fixtures: área temporária em todo teste (nada é escrito na skill); modelos via VDIA_MODELOS, sem copiar."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from vdia import config, voz


@pytest.fixture(autouse=True)
def area(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    monkeypatch.setenv("VDIA_AREA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture
def com_vozes() -> list[voz.EntradaVoz]:
    if not os.environ.get("VDIA_MODELOS"):
        pytest.skip("defina VDIA_MODELOS com a pasta dos modelos de voz")
    inst = voz.instaladas()
    if not inst:
        pytest.skip(f"nenhuma voz em {config.pasta_modelos()}")
    return inst
