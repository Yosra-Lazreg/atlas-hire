.PHONY: install build dashboard test lint

install:
	python -m pip install -e ".[dev]"

build:
	atlashire build --as-of 2026-09-13

dashboard:
	streamlit run app/streamlit_app.py

test:
	pytest -q

lint:
	ruff check src tests app
