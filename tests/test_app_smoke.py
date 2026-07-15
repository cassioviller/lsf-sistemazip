"""A fábrica se recusa a subir sem segredo de sessão — login com segredo default
é login decorativo."""
import pytest


def test_app_exige_segredo_de_sessao(app_db, monkeypatch):
    monkeypatch.delenv("LSF_SECRET", raising=False)
    from app.main import criar_app

    with pytest.raises(RuntimeError, match="LSF_SECRET"):
        criar_app(app_db)


def test_app_sobe_com_segredo(app_db):
    from app.main import criar_app

    app = criar_app(app_db, secret="qualquer-coisa-longa")
    # FastAPI 0.139 embrulha include_router em _IncludedRouter (sem .path):
    # achatar até as rotas do router original.
    rotas = set()
    for r in app.routes:
        if hasattr(r, "path"):
            rotas.add(r.path)
        else:
            original = getattr(r, "original_router", None)
            rotas.update(s.path for s in getattr(original, "routes", []))
    assert "/login" in rotas
    assert "/projetos" in rotas
    assert "/p/{token}" in rotas
