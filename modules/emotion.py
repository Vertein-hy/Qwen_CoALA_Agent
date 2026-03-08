"""Emotion engine module.

Single responsibility: infer current mood label for prompt conditioning.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.llm_interface import LLMInterface


@dataclass
class EmotionEngine:
    llm: LLMInterface
    current_mood: str = "Curious"

    valid_emotions: tuple[str, ...] = (
        "Happy",
        "Sad",
        "Angry",
        "Curious",
        "Neutral",
        "Excited",
    )

    def update_mood(self, user_input: str, recent_memories: list[str]) -> str:
        prompt = (
            "You are an emotion classifier. "
            "Choose exactly one label from: "
            f"{', '.join(self.valid_emotions)}.\n"
            f"Current mood: {self.current_mood}\n"
            f"User input: {user_input}\n"
            f"Recent memories: {recent_memories}\n"
            "Output label only."
        )

        try:
            result = self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                route_hint="small",
            ).strip()
        except Exception:
            return self.current_mood

        for emotion in self.valid_emotions:
            if emotion.lower() in result.lower():
                self.current_mood = emotion
                return self.current_mood

        return self.current_mood
