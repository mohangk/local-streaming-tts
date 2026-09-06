from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectOption:
    value: str | float
    label: str
    language: str | None = None


@dataclass(frozen=True)
class InstructionModelCapabilities:
    option: SelectOption
    voices: tuple[SelectOption, ...]
    supports_instructions: bool = True


@dataclass(frozen=True)
class InstructionSampleCapabilities:
    models: tuple[InstructionModelCapabilities, ...]
    speeds: tuple[SelectOption, ...]
    default_model: str
    default_voice: str


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

QWEN_INSTRUCTION_MODELS: tuple[SelectOption, ...] = (
    SelectOption("qwen3-tts-instruct-flash-realtime", "Qwen3 TTS Instruct Flash Realtime"),
    SelectOption(
        "qwen3-tts-instruct-flash-realtime-2026-01-22",
        "Qwen3 TTS Instruct Flash Realtime 2026-01-22",
    ),
)

QWEN_INSTRUCTION_VOICES: tuple[SelectOption, ...] = (
    SelectOption("Cherry", "Cherry - friendly natural woman"),
    SelectOption("Serena", "Serena - gentle young woman"),
    SelectOption("Ethan", "Ethan - warm energetic man"),
    SelectOption("Chelsie", "Chelsie - bright animated woman"),
    SelectOption("Momo", "Momo - playful woman"),
    SelectOption("Vivian", "Vivian - confident woman"),
    SelectOption("Moon", "Moon - bold man"),
    SelectOption("Maia", "Maia - gentle thoughtful woman"),
    SelectOption("Kai", "Kai - soothing man"),
    SelectOption("Nofish", "Nofish - casual man"),
    SelectOption("Bella", "Bella - playful young woman"),
    SelectOption("Eldric Sage", "Eldric Sage - calm wise elder"),
    SelectOption("Mia", "Mia - soft gentle woman"),
    SelectOption("Mochi", "Mochi - quick-witted man"),
    SelectOption("Bellona", "Bellona - powerful clear voice"),
    SelectOption("Vincent", "Vincent - raspy heroic man"),
    SelectOption("Bunny", "Bunny - playful young girl"),
    SelectOption("Neil", "Neil - precise professional man"),
    SelectOption("Elias", "Elias - academic storyteller"),
    SelectOption("Arthur", "Arthur - earthy storyteller"),
    SelectOption("Nini", "Nini - soft sweet woman"),
    SelectOption("Seren", "Seren - gentle soothing woman"),
    SelectOption("Pip", "Pip - playful young boy"),
    SelectOption("Stella", "Stella - expressive young woman"),
)

SPEED_OPTIONS: tuple[SelectOption, ...] = (
    SelectOption(0.75, "0.75x"),
    SelectOption(0.9, "0.9x"),
    SelectOption(1.0, "1x"),
    SelectOption(1.1, "1.1x"),
    SelectOption(1.25, "1.25x"),
    SelectOption(1.5, "1.5x"),
)

QWEN_INSTRUCTION_SAMPLE_CAPABILITIES = InstructionSampleCapabilities(
    models=tuple(
        InstructionModelCapabilities(option=model, voices=QWEN_INSTRUCTION_VOICES)
        for model in QWEN_INSTRUCTION_MODELS
    ) + (InstructionModelCapabilities(
        option=SelectOption("qwen3-tts-flash-realtime", "Qwen3 TTS Flash Realtime (legacy, no instructions)"),
        voices=QWEN_ENGLISH_VOICES, supports_instructions=False,
    ),),
    speeds=SPEED_OPTIONS,
    default_model="qwen3-tts-instruct-flash-realtime",
    default_voice="Kai",
)
