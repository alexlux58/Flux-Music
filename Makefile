SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

PYTHON ?= .venv/Scripts/python
ifeq ($(OS),Windows_NT)
  PYTHON := .venv/Scripts/python.exe
  VENV_PY := .venv/Scripts/python.exe
else
  PYTHON := .venv/bin/python
  VENV_PY := .venv/bin/python
endif

.PHONY: help setup lint test syntax check run web build

help:
	@echo "Music Library targets:"
	@echo "  make setup   # create venv and install deps"
	@echo "  make check   # lint + tests"
	@echo "  make run     # desktop + web companion"
	@echo "  make web     # web-only (any device)"
	@echo "  make build   # PyInstaller Windows build"

setup:
	python -m venv .venv
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -e ".[dev,build]"

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests

test:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest

syntax:
	$(PYTHON) -c "from src.app import create_app; create_app(); print('ok')"

check: lint test syntax

run:
	$(PYTHON) -m src.main

web:
	$(PYTHON) -m src.main --web-only

build:
	$(PYTHON) -m PyInstaller MusicLibrary.spec --distpath dist-bpm --workpath build-bpm
