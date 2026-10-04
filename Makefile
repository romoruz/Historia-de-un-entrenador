.PHONY: test lint semana1 figuras verificar-figuras
test:
	.venv/bin/pytest -q
lint:
	.venv/bin/ruff check src tests
# Semana 1 de punta a punta (ver docs/00_ROADMAP.md)
semana1:
	.venv/bin/dtcoach aplanar
	.venv/bin/dtcoach partidos
	.venv/bin/dtcoach fase0
	.venv/bin/dtcoach cv-k
# Copia a docs/figuras/ las figuras que enlazan los documentos (reports/ no se versiona) y verifica enlaces y peso
figuras:
	bash scripts/publicar_figuras.sh
verificar-figuras:
	.venv/bin/python scripts/verificar_figuras.py --max-mb 20
