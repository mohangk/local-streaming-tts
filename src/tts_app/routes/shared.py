from __future__ import annotations

from fastapi import BackgroundTasks

from tts_app.generation import GenerationService


async def schedule_generation(
    service: GenerationService,
    generation_id: int,
    voice: str,
    speed: float,
    language: str,
    background_tasks: BackgroundTasks,
    run_background_inline: bool,
) -> None:
    if run_background_inline:
        await service.run_generation(generation_id, voice, speed, language)
        return
    background_tasks.add_task(service.run_generation, generation_id, voice, speed, language)
