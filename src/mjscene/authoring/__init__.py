"""Authoring layer for people and AI tools.

    from mjscene.authoring import TEMPLATES, get_template, build_prompt

Scenes in `templates` support `mjscene new -t <name>` and provide examples for
LLMs. `prompt` builds the system prompt from the live `library` vocabulary.
"""

from __future__ import annotations

from .prompt import build_prompt
from .templates import TEMPLATES
from .templates import get as get_template

__all__ = ["TEMPLATES", "get_template", "build_prompt"]
