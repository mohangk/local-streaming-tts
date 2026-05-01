from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectOption:
    value: str | float
    label: str


QWEN_ENGLISH_VOICES: tuple[SelectOption, ...] = (
    SelectOption("Jennifer", "Jennifer - American English female"),
    SelectOption("Aiden", "Aiden - American English male"),
    SelectOption("Neil", "Neil - professional news male"),
    SelectOption("Andre", "Andre - natural steady male"),
    SelectOption("Ryan", "Ryan - dramatic male"),
    SelectOption("Cherry", "Cherry - friendly young woman"),
    SelectOption("Serena", "Serena - gentle young woman"),
    SelectOption("Ethan", "Ethan - warm energetic male"),
    SelectOption("Chelsie", "Chelsie - bright young woman"),
    SelectOption("Momo", "Momo - playful woman"),
    SelectOption("Vivian", "Vivian - confident woman"),
    SelectOption("Moon", "Moon - bold male"),
    SelectOption("Maia", "Maia - gentle thoughtful woman"),
    SelectOption("Kai", "Kai - soothing male"),
    SelectOption("Mia", "Mia - soft gentle woman"),
    SelectOption("Mochi", "Mochi - quick-witted male"),
    SelectOption("Bellona", "Bellona - powerful clear voice"),
    SelectOption("Vincent", "Vincent - raspy heroic male"),
    SelectOption("Eldric Sage", "Eldric Sage - wise elder male"),
    SelectOption("Katerina", "Katerina - mature rhythmic woman"),
    SelectOption("Nofish", "Nofish - casual male"),
    SelectOption("Bella", "Bella - youthful woman"),
    SelectOption("Arthur", "Arthur - earthy storyteller male"),
    SelectOption("Nini", "Nini - soft sweet woman"),
    SelectOption("Seren", "Seren - soothing woman"),
    SelectOption("Bodega", "Bodega - Spanish male"),
    SelectOption("Sonrisa", "Sonrisa - Latin American woman"),
    SelectOption("Dolce", "Dolce - Italian male"),
)

SPEED_OPTIONS: tuple[SelectOption, ...] = (
    SelectOption(0.75, "0.75x"),
    SelectOption(0.9, "0.9x"),
    SelectOption(1.0, "1x"),
    SelectOption(1.1, "1.1x"),
    SelectOption(1.25, "1.25x"),
    SelectOption(1.5, "1.5x"),
)
