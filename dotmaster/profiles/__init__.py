"""
dotmaster/profiles/__init__.py
Preset profile registry.

A profile is a dict of default config values that pre-populates the wizard.
Users can still override any value; profiles are starting points, not lock-ins.
"""
from __future__ import annotations

from dotmaster.profiles.backend_api import BACKEND_API_PROFILE
from dotmaster.profiles.library import LIBRARY_PROFILE
from dotmaster.profiles.monorepo import MONOREPO_PROFILE
from dotmaster.profiles.web_app import WEB_APP_PROFILE

# Human-readable metadata shown with `dotmaster profile <name>`
PROFILE_META: dict[str, dict] = {
    "web_app": {
        "label": "Web App",
        "description": "Full-stack web application (React/Next.js + ESLint + Prettier + Docker + CI)",
        "data": WEB_APP_PROFILE,
    },
    "library": {
        "label": "Library",
        "description": "Reusable JS/TS library or Python package (ESLint/Ruff + Tests, no Docker)",
        "data": LIBRARY_PROFILE,
    },
    "backend_api": {
        "label": "Backend API",
        "description": "REST/GraphQL API service (Python FastAPI + Ruff + Black + Docker + CI)",
        "data": BACKEND_API_PROFILE,
    },
    "monorepo": {
        "label": "Monorepo",
        "description": "Multi-package monorepo (pnpm + ESLint + Prettier + CI)",
        "data": MONOREPO_PROFILE,
    },
}


def get_profile(name: str) -> dict | None:
    """Return the profile data dict for *name*, or None if not found."""
    entry = PROFILE_META.get(name)
    return entry["data"] if entry else None


def list_profiles() -> list[tuple[str, str]]:
    """Return list of (name, description) tuples for all profiles."""
    return [(k, v["description"]) for k, v in PROFILE_META.items()]
