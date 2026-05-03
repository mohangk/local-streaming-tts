from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectOption:
    value: str | float
    label: str
    language: str | None = None


QWEN_ENGLISH_VOICES: tuple[SelectOption, ...] = (
    SelectOption("Jennifer", "Jennifer - American English female", language="en"),
    SelectOption("Aiden", "Aiden - American English male", language="en"),
    SelectOption("Neil", "Neil - professional news male", language="en"),
    SelectOption("Andre", "Andre - natural steady male", language="en"),
    SelectOption("Ryan", "Ryan - dramatic male", language="en"),
    SelectOption("Cherry", "Cherry - friendly young woman", language="en"),
    SelectOption("Serena", "Serena - gentle young woman", language="en"),
    SelectOption("Ethan", "Ethan - warm energetic male", language="en"),
    SelectOption("Chelsie", "Chelsie - bright young woman", language="en"),
    SelectOption("Momo", "Momo - playful woman", language="en"),
    SelectOption("Vivian", "Vivian - confident woman", language="en"),
    SelectOption("Moon", "Moon - bold male", language="en"),
    SelectOption("Maia", "Maia - gentle thoughtful woman", language="en"),
    SelectOption("Kai", "Kai - soothing male", language="en"),
    SelectOption("Mia", "Mia - soft gentle woman", language="en"),
    SelectOption("Mochi", "Mochi - quick-witted male", language="en"),
    SelectOption("Bellona", "Bellona - powerful clear voice", language="en"),
    SelectOption("Vincent", "Vincent - raspy heroic male", language="en"),
    SelectOption("Eldric Sage", "Eldric Sage - wise elder male", language="en"),
    SelectOption("Katerina", "Katerina - mature rhythmic woman", language="en"),
    SelectOption("Nofish", "Nofish - casual male", language="en"),
    SelectOption("Bella", "Bella - youthful woman", language="en"),
    SelectOption("Arthur", "Arthur - earthy storyteller male", language="en"),
    SelectOption("Nini", "Nini - soft sweet woman", language="en"),
    SelectOption("Seren", "Seren - soothing woman", language="en"),
    SelectOption("Bodega", "Bodega - Spanish male", language="en"),
    SelectOption("Sonrisa", "Sonrisa - Latin American woman", language="en"),
    SelectOption("Dolce", "Dolce - Italian male", language="en"),
)

QWEN_CHINESE_VOICES: tuple[SelectOption, ...] = tuple(
    SelectOption(str(option.value), f"{option.value} - Mandarin Chinese", language="zh")
    for option in QWEN_ENGLISH_VOICES
)

SPEED_OPTIONS: tuple[SelectOption, ...] = (
    SelectOption(0.75, "0.75x"),
    SelectOption(0.9, "0.9x"),
    SelectOption(1.0, "1x"),
    SelectOption(1.1, "1.1x"),
    SelectOption(1.25, "1.25x"),
    SelectOption(1.5, "1.5x"),
)
