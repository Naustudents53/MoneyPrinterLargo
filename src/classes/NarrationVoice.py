class NarrationVoice:
    """Lightweight prompt guardrails for a natural spoken narrator."""

    @staticmethod
    def short_generation_directive(language: str) -> str:
        return f"""

NATURAL NARRATION GUIDE:
- Keep the existing hook and retention structure. This is a guardrail, not a separate rewrite brief.
- Sound like one curious person explaining a strange thing clearly in {language}, not like an announcer, ad, or encyclopedia.
- Add one concrete anchor early: what is seen, measured, touched, heard, or physically changing.
- Name the main subject early. A mystery hook can come first, but by sentence 2 the viewer should know the object, place, person, event, or phenomenon being discussed.
- Let the story move through cause, consequence, and reveal. Avoid a list-of-facts cadence.
- Use plain spoken transitions only when they fit naturally, like "pero", "lo raro es", "por eso", or their equivalent in {language}.
- Let some sentences be calm and simple. Do not make every line sound catastrophic.
- The final line should feel like a payoff, not a summary. It should echo the opening image and make replay feel intentional.
- Never narrate internal structure labels like "primera revelacion", "segunda revelacion", "hook", "contexto", "desarrollo", "conclusion", "parte uno", or "seccion dos".
- No calls to action inside the narration.
"""

    @staticmethod
    def rewrite_guardrail(language: str) -> str:
        return f"""

NATURAL VOICE GUARDRAIL:
- Preserve the original narrator voice while improving retention.
- Change only what helps clarity, causality, pacing, or a stronger reveal.
- Keep the subject named early and the final line connected to the opening image.
- Do not turn the script into slogans, hype phrases, or motivational trailer copy.
- Remove any internal structure label; the narrator must not say "primera revelacion", "segunda revelacion", "hook", "contexto", "desarrollo", "conclusion", "parte uno", or "seccion dos".
- Keep natural spoken {language}; no calls to action, no stage directions.
"""

    @staticmethod
    def long_generation_directive(language: str) -> str:
        return f"""

DOCUMENTARY VOICE GUIDE:
- Use a close, curious documentary voice in {language}; informed, but still conversational.
- Anchor each section in observable details, decisions, instruments, places, or physical consequences.
- Build tension by asking better questions and following cause and effect, not by stacking dramatic adjectives.
- Vary rhythm naturally: a few short lines, then a fuller explanation when the idea needs room.
- Never narrate section labels or structure labels; markers like intro, section, first revelation, climax, or conclusion are private writing instructions only.
- If an outro call to action is required, keep it warm and brief so it does not break the story.
"""
