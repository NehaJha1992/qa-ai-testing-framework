# Convenience shortcuts for macOS/Linux (or Windows with make installed).
# Without make, see the plain commands in README.md.
ifeq ($(OS),Windows_NT)
    VENV_BIN = .venv/Scripts
else
    VENV_BIN = .venv/bin
endif
PYTHON = $(VENV_BIN)/python
PYTEST = $(VENV_BIN)/pytest

.PHONY: install test test-api test-ui test-smoke test-mcp test-perf report

install:
	python3 -m venv .venv || py -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install chromium

test:
	$(PYTEST)

test-api:
	$(PYTEST) -m api

test-ui:
	$(PYTEST) -m ui

test-smoke:
	$(PYTEST) -m smoke

test-mcp:
	$(PYTEST) -m mcp

# Load test with Locust (starts its own mock app, takes about 30 seconds)
test-perf:
	$(PYTHON) performance/run_perf.py

# Open the HTML report in the default browser (any OS)
report:
	$(PYTHON) -c "import webbrowser, pathlib; webbrowser.open(pathlib.Path('reports/report.html').resolve().as_uri())"
