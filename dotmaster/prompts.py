"""
dotmaster/prompts.py
The Prompter protocol — the seam between the wizard's *questions* and how
they're actually asked.

Splitting this out is what makes the wizard testable (inject a
:class:`ScriptedPrompter` instead of a real terminal) and what makes
``dotmaster init --yes`` possible (:class:`DefaultPrompter` never blocks).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Choice:
    value: str
    label: str
    enabled: bool = False


class Prompter(Protocol):
    def text(self, message: str, *, default: str = "") -> str: ...

    def confirm(self, message: str, *, default: bool = False) -> bool: ...

    def select(self, message: str, choices: Sequence[Choice], *, default: str = "") -> str: ...

    def checkbox(
        self, message: str, choices: Sequence[Choice], *, required: bool = False
    ) -> list[str]: ...


class InquirerPrompter:
    """Real terminal prompts via InquirerPy — used interactively."""

    def text(self, message: str, *, default: str = "") -> str:
        from InquirerPy import inquirer

        return inquirer.text(message=message, default=default).execute().strip()

    def confirm(self, message: str, *, default: bool = False) -> bool:
        from InquirerPy import inquirer

        return inquirer.confirm(message=message, default=default).execute()

    def select(self, message: str, choices: Sequence[Choice], *, default: str = "") -> str:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice as IChoice

        options = [IChoice(c.value, c.label) for c in choices]
        chosen_default = default or (choices[0].value if choices else "")
        return inquirer.select(message=message, choices=options, default=chosen_default).execute()

    def checkbox(
        self, message: str, choices: Sequence[Choice], *, required: bool = False
    ) -> list[str]:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice as IChoice

        options = [IChoice(c.value, c.label, enabled=c.enabled) for c in choices]
        validate = (lambda result: len(result) > 0) if required else None
        return inquirer.checkbox(
            message=message,
            choices=options,
            validate=validate,
            invalid_message="Please select at least one option.",
            instruction="(space to select, enter to confirm)",
        ).execute()


class DefaultPrompter:
    """
    Never blocks: every question resolves to its default.

    Used for ``dotmaster init --yes`` and in any non-TTY environment, so
    dotmaster works in CI, Docker builds and scripts without special-casing.
    """

    def text(self, message: str, *, default: str = "") -> str:
        return default

    def confirm(self, message: str, *, default: bool = False) -> bool:
        return default

    def select(self, message: str, choices: Sequence[Choice], *, default: str = "") -> str:
        if default:
            return default
        return choices[0].value if choices else ""

    def checkbox(
        self, message: str, choices: Sequence[Choice], *, required: bool = False
    ) -> list[str]:
        preselected = [c.value for c in choices if c.enabled]
        if preselected:
            return preselected
        return [choices[0].value] if required and choices else []


class ScriptedPrompter:
    """Replays a fixed sequence of answers — for tests."""

    def __init__(self, answers: Sequence[object]) -> None:
        self._answers = list(answers)
        self._i = 0

    def _next(self):
        if self._i >= len(self._answers):
            raise AssertionError("ScriptedPrompter ran out of answers")
        value = self._answers[self._i]
        self._i += 1
        return value

    def text(self, message: str, *, default: str = "") -> str:
        return str(self._next())

    def confirm(self, message: str, *, default: bool = False) -> bool:
        return bool(self._next())

    def select(self, message: str, choices: Sequence[Choice], *, default: str = "") -> str:
        return str(self._next())

    def checkbox(
        self, message: str, choices: Sequence[Choice], *, required: bool = False
    ) -> list[str]:
        return list(self._next())
