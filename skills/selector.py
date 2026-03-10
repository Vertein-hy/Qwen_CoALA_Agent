"""Skill candidate selection utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills.manager import SkillManager


@dataclass(frozen=True)
class SkillCandidate:
    """One ranked skill candidate for a user query."""

    name: str
    score: float
    source_excerpt: str


class SkillSelector:
    """Recommend existing internalized skills for the current task."""

    _TOKEN_PATTERN = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", re.IGNORECASE)

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager

    def recommend(self, query: str, top_k: int = 3) -> list[SkillCandidate]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        query_tokens = self._tokenize(normalized_query)
        candidates: list[SkillCandidate] = []
        for record in self.skill_manager.catalog.list_records():
            if not record.enabled:
                continue
            score = self._score_record(
                query=normalized_query,
                query_tokens=query_tokens,
                skill_name=record.name,
                source_text=record.source,
            )
            if score <= 0:
                continue
            source_excerpt = record.source.replace("\n", " ").strip()[:120]
            candidates.append(
                SkillCandidate(
                    name=record.name,
                    score=score,
                    source_excerpt=source_excerpt,
                )
            )

        candidates.sort(key=lambda item: (-item.score, item.name))
        return candidates[: max(0, top_k)]

    def has_skill(self, name: str) -> bool:
        return self.skill_manager.has_skill(name)

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        return {token.lower() for token in cls._TOKEN_PATTERN.findall(text) if token.strip()}

    def _score_record(
        self,
        *,
        query: str,
        query_tokens: set[str],
        skill_name: str,
        source_text: str,
    ) -> float:
        score = 0.0
        skill_name_lower = skill_name.lower()
        if skill_name_lower in query:
            score += 6.0

        name_parts = [part for part in skill_name_lower.split("_") if part]
        for part in name_parts:
            if part in query:
                score += 1.5

        source_lower = source_text.lower()
        source_tokens = self._tokenize(source_lower)
        overlap = query_tokens & source_tokens
        score += 0.8 * len(overlap)
        return score
