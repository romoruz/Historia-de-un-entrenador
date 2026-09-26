"""El CLI arma su parser completo y cada subcomando apunta a una función que existe.

Regresión: al editar cli.py se borraron cmd_decisiones y cmd_simulador sin que
ninguna prueba lo notara (ninguna importaba el CLI)."""
import pytest

from dtcoach import cli

COMANDOS = ["aplanar", "partidos", "fase0", "cv-k", "mezcla", "reproducibilidad", "curva-k", "bondad",
            "elo", "fase2", "fase3", "atlas", "decisiones", "simulador", "mallado", "markov", "comparar-paso"]


@pytest.mark.parametrize("cmd", COMANDOS)
def test_cada_subcomando_existe_y_tiene_ayuda(cmd, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main([cmd, "--help"])
    assert e.value.code == 0
    assert cmd in capsys.readouterr().out


def test_las_funciones_de_los_comandos_existen():
    for nombre in ("cmd_fase2", "cmd_fase3", "cmd_atlas", "cmd_decisiones", "cmd_simulador", "cmd_elo"):
        assert callable(getattr(cli, nombre))
