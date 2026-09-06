from tts_app.synthesis import SAMPLE_TEXT

AUDIOBOOK_INSTRUCTIONS = 'Read in a calm long-form audiobook style. Use clear articulation, steady pacing, low vocal fatigue, natural sentence endings, and restrained expressiveness. Avoid theatrical delivery, sales energy, exaggerated intonation, whispering, vocal fry, or sharp news-anchor emphasis.'


def default_profiles(capabilities):
    return [dict(name=name, model=capabilities.default_model, voice=capabilities.default_voice,
                 language=language, speed=1.0, instructions=AUDIOBOOK_INSTRUCTIONS,
                 preview_text=SAMPLE_TEXT[language])
            for language, name in [('en', 'English audiobook'), ('zh', 'Chinese audiobook')]]
