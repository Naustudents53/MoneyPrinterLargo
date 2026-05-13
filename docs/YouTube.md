# YouTube Shorts Automater

MoneyPrinter Pro automates the full Shorts pipeline: topic → script → metadata → image generation (AI or stock photos) → TTS → subtitles → MoviePy composition → Selenium upload to YouTube Studio.

Visuals can come from either AI generators (Gemini Nano Banana 2, Leonardo AI) or curated stock sources (Wikimedia, Europeana, Library of Congress, Pexels, Pixabay) depending on the niche. Music is layered in from the bundled songs library.

## Relevant Configuration

In your `config.json`, you need the following attributes filled out, so that the bot can function correctly.

```json
{
  "firefox_profile": "The path to your Firefox profile (used to log in to YouTube)",
  "headless": true,
  "llm": "The Large Language Model you want to use to generate the video script.",
  "image_model": "What AI Model you want to use to generate images.",
  "threads": 4,
  "is_for_kids": true
}
```

## Roadmap

Here are some features that are planned for the future:

- [ ] Subtitles (using either AssemblyAI or locally assembling them)
