.PHONY: test lint semana1
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
