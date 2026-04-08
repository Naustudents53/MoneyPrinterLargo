import re
import base64
import json
import time
import os
import requests
import assemblyai as aai

from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from config import *
from status import *
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language

        self.images = []
        self._used_stock_urls: set = set()
        self.word_timestamps = None

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        # Copy the profile so we can use it even if Firefox is open.
        # We must preserve cookies, logins, and session data for YouTube.
        import shutil
        import tempfile
        self._temp_profile_dir = tempfile.mkdtemp(prefix="mpv2_firefox_")
        temp_profile = os.path.join(self._temp_profile_dir, "profile")
        if get_verbose():
            info(f" => Copying Firefox profile to temp dir...")
        # Exclude lock files and large caches that cause conflicts,
        # but KEEP cookies.sqlite, logins.json, key4.db, etc.
        shutil.copytree(
            self._fp_profile_path, temp_profile,
            ignore=shutil.ignore_patterns(
                "lock", ".parentlock", "parent.lock",
                "cache2", "startupCache", "shader-cache",
                "thumbnails", "storage", "crashes",
            ),
            dirs_exist_ok=False,
        )
        # Remove the session restore files that can cause crashes
        for bad_file in ["sessionstore.jsonlz4", "sessionstore-backups"]:
            bad_path = os.path.join(temp_profile, bad_file)
            if os.path.isfile(bad_path):
                os.remove(bad_path)
            elif os.path.isdir(bad_path):
                shutil.rmtree(bad_path, ignore_errors=True)

        self.options.add_argument("-profile")
        self.options.add_argument(temp_profile)

        # Browser is initialized lazily just before upload (see _ensure_browser)
        self.browser: webdriver.Firefox = None

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name)

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.
        Avoids repeating topics from previously uploaded videos.

        Returns:
            topic (str): The generated topic.
        """
        # Gather previous video titles to avoid repetition
        previous_topics = ""
        try:
            videos = self.get_videos()
            if videos:
                topics = [v.get("subject") or v.get("title") for v in videos if v.get("subject") or v.get("title")]
                if topics:
                    recent = topics[-15:]  # last 15 to keep prompt manageable
                    previous_topics = "\n\nIMPORTANT: Do NOT repeat or rephrase any of these previously made videos:\n" + "\n".join(f"- {t}" for t in recent) + "\n\nGenerate a COMPLETELY DIFFERENT and ORIGINAL idea."
        except Exception:
            pass

        import random
        creativity_seed = random.randint(1, 100000)
        completion = self.generate_response(
            f"""Generate ONE specific, focused topic for a short video.

YOUR NICHE (you MUST stay strictly within this niche): {self.niche}

CRITICAL RULE: The topic MUST be directly and obviously related to the niche above. Do NOT generate topics about unrelated subjects like history, politics, celebrities, cinema, or any field outside the niche. If the niche is about the universe and the mind, the topic must be about the universe and the mind — NOT about historical figures, civilizations, or unrelated events.

The topic must be ONE concrete story, event, mystery, or fact — NOT a broad category.

BAD example: "Curiosidades del antiguo Egipto" (too broad, leads to random facts)
GOOD example: "La maldición de la tumba de Tutankamón: ¿qué les pasó a los arqueólogos?" (one specific story)
GOOD example: "¿Por qué los romanos usaban orina para lavar la ropa?" (one specific curiosity)
GOOD example: "El día que un asteroide exterminó al 75% de la vida en la Tierra" (one specific event)

Return ONLY the topic in one sentence. Write in {self.language}. Nothing else.{previous_topics}

(Creativity seed: {creativity_seed} — use this to inspire a unique, unexpected angle.)"""
        )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion

        return completion

    def generate_script(self) -> str:
        """
        Generate a script for a video, depending on the subject of the video, the number of paragraphs, and the AI model.

        Returns:
            script (str): The script of the video.
        """
        sentence_length = get_script_sentence_length()
        prompt = f"""Write a narration script for a short video in EXACTLY {sentence_length} sentences.

TOPIC: {self.subject}

NARRATIVE STRUCTURE (follow this order):
1. HOOK (sentence 1): Start with a question or shocking fact that grabs attention. Examples: "¿Sabías que...?", "¿Qué pasaría si...?", "Imagina que...", "Hay algo que nadie te contó sobre..."
2. CONTEXT (sentences 2-3): Set the scene. When and where does this happen? What's the background?
3. DEVELOPMENT (sentences 4-{sentence_length - 2}): Go deeper into the topic. Reveal details, facts, consequences. Build tension or curiosity. Each sentence should ADVANCE the story, not jump to unrelated facts.
4. CONCLUSION (last 1-2 sentences): End with a powerful thought, a twist, or a mind-blowing takeaway.

CRITICAL RULES:
- Stay on ONE topic throughout. Do NOT list random facts. Tell ONE story from start to finish.
- Every sentence must connect to the previous one. The script must feel like a continuous narrative, not a list.
- EXACTLY {sentence_length} sentences. Short and punchy (under 20 words each).
- NO markdown, NO formatting, NO titles, NO bullet points.
- NO "welcome", NO "voiceover", NO meta-references.
- ONLY return the raw script text. Nothing else.
- WRITE ENTIRELY IN {self.language}. Every word must be in {self.language}.
"""
        completion = self.generate_response(prompt)

        # Apply regex to remove *
        completion = re.sub(r"\*", "", completion)

        if not completion:
            error("The generated script is empty.")
            return

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion

        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        title = self.generate_response(
            f"Please generate a YouTube Video Title for the following subject: {self.subject}. "
            f"Optionally include 1-2 relevant hashtags at the end (but only if they fit naturally). "
            f"Only return the title, nothing else. Limit the title under 80 characters. Be concise. "
            f"YOU MUST WRITE THE TITLE IN {self.language}. Do NOT wrap the title in quotes. Do NOT start or end with any quote character."
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

        # If truncation would cut a hashtag, remove hashtags instead
        if len(title) > 100:
            if "#" in title:
                title = title[:title.index("#")].strip()
            if len(title) > 100:
                title = title[:100]

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else. Do NOT wrap the description in quotes. Do NOT start or end with any quote character. YOU MUST WRITE THE DESCRIPTION IN {self.language}."
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        description = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self) -> List[str]:
        """
        Generates AI Image Prompts based on the provided Video Script.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = 6

        # Split script into sections so the LLM knows exactly what each image must show
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', self.script) if s.strip()]
        sections = []
        per_section = max(1, len(sentences) // n_prompts)
        for i in range(n_prompts):
            start = i * per_section
            end = start + per_section if i < n_prompts - 1 else len(sentences)
            section_text = ' '.join(sentences[start:end])
            if section_text:
                sections.append(section_text)
        # Pad if we got fewer sections
        while len(sections) < n_prompts:
            sections.append(self.subject)

        sections_text = ""
        for i, sec in enumerate(sections):
            sections_text += f"\nSECTION {i+1}: \"{sec}\"\n"

        prompt = f"""Generate exactly {n_prompts} image prompts for a video about: {self.subject}

The script has been divided into {n_prompts} sections. Each image MUST match its section:
{sections_text}
INSTRUCTIONS:
- Image 1 MUST illustrate SECTION 1, Image 2 MUST illustrate SECTION 2, etc.
- Describe the LITERAL content of each section as a visual scene.
- Example: if a section says "The ancient Egyptians built massive pyramids", write: "Massive Egyptian pyramids under construction, thousands of workers pulling limestone blocks, desert sand, blue sky, cranes made of wood, cinematic wide angle"
- Be SPECIFIC: name real things (animals, buildings, objects, places, people).
- Include: camera angle, lighting, colors, environment details.
- Write in English. Each prompt: 30-60 words.
- FORBIDDEN: visualization, concept, essence, metaphor, abstract, symbolic, interpretation.

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        image_prompts = []

        # Try to extract JSON array from the response
        try:
            parsed = json.loads(completion)
            if isinstance(parsed, list):
                image_prompts = [str(p) for p in parsed if isinstance(p, str)]
            elif isinstance(parsed, dict) and "image_prompts" in parsed:
                image_prompts = parsed["image_prompts"]
        except Exception:
            # Try to find a JSON array in the response
            match = re.search(r'\[.*?\]', completion, re.DOTALL)
            if match:
                try:
                    image_prompts = json.loads(match.group())
                except Exception:
                    pass

        # Fallback if parsing failed or too few prompts
        fallback_prompts = [
            f"{self.subject}, realistic photograph, wide angle, natural lighting, highly detailed, 8K",
            f"{self.subject}, close-up detail shot, soft natural light, vivid colors, photorealistic",
            f"{self.subject}, panoramic landscape view, golden hour, cinematic composition, detailed",
            f"{self.subject}, historical illustration style, warm earth tones, detailed environment",
            f"{self.subject}, overhead aerial perspective, dramatic clouds, vast scale, ultra detailed",
            f"{self.subject}, documentary photograph, authentic setting, natural atmosphere, 4K quality",
        ]

        if not image_prompts or not isinstance(image_prompts, list):
            if get_verbose():
                warning("Failed to parse image prompts, using fallback prompts")
            image_prompts = fallback_prompts
        elif len(image_prompts) < n_prompts:
            if get_verbose():
                warning(f"Only got {len(image_prompts)} prompts, padding to {n_prompts}")
            # Pad with fallback prompts to reach n_prompts
            for fp in fallback_prompts:
                if len(image_prompts) >= n_prompts:
                    break
                image_prompts.append(fp)

        # Limit to n_prompts
        image_prompts = image_prompts[:n_prompts]

        if get_verbose():
            info(f" => Generated Image Prompts: {image_prompts}")

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in .mp.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.images.append(image_path)
        return image_path

    def _try_huggingface(self, prompt: str) -> bytes:
        """Try HuggingFace Inference API. Requires free HF token."""
        from config import get_hf_api_key
        hf_token = get_hf_api_key()
        if not hf_token:
            raise RuntimeError("HuggingFace token not configured (hf_api_key in config.json)")

        print(colored(f"    [HuggingFace] Generating...", "cyan"), flush=True)
        headers = {"Authorization": f"Bearer {hf_token}"}

        models = [
            "stabilityai/stable-diffusion-xl-base-1.0",
        ]

        for model in models:
            try:
                resp = requests.post(
                    f"https://router.huggingface.co/hf-inference/models/{model}",
                    headers=headers,
                    json={"inputs": prompt[:300]},
                    timeout=120,
                )
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and ("image" in ct or len(resp.content) > 5000):
                    print(colored("OK", "green"))
                    return resp.content
            except Exception:
                continue
        raise RuntimeError("HuggingFace: all models failed")

    def _try_pollinations(self, prompt: str) -> bytes:
        """Try Pollinations.ai image generation (primary provider - free, no key, best quality with flux model)."""
        import urllib.parse
        short_prompt = prompt[:500]
        encoded = urllib.parse.quote(short_prompt)
        seed = int(time.time())
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}&model=flux"
        print(colored(f"    [Pollinations.ai FLUX] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations returned status {resp.status_code}")

    def _try_pollinations_turbo(self, prompt: str) -> bytes:
        """Try Pollinations.ai with turbo model (faster, more available than FLUX)."""
        import urllib.parse
        short_prompt = prompt[:500]
        encoded = urllib.parse.quote(short_prompt)
        seed = int(time.time()) + 42
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}&model=turbo"
        print(colored(f"    [Pollinations turbo] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations turbo returned status {resp.status_code}")

    def _try_pollinations_realism(self, prompt: str) -> bytes:
        """Try Pollinations.ai with flux-realism model (photorealistic style)."""
        import urllib.parse
        short_prompt = prompt[:500]
        encoded = urllib.parse.quote(short_prompt)
        seed = int(time.time()) + 99
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={seed}&model=flux-realism"
        print(colored(f"    [Pollinations flux-realism] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations flux-realism returned status {resp.status_code}")

    def _try_ideogram(self, prompt: str) -> bytes:
        """Try Ideogram API (very high quality, free tier ~25 images/day)."""
        from config import get_ideogram_api_key
        api_key = get_ideogram_api_key()
        if not api_key:
            raise RuntimeError("Ideogram API key not configured")

        print(colored(f"    [Ideogram] Generating...", "cyan"), flush=True)
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        payload = {
            "image_request": {
                "prompt": prompt[:1000],
                "model": "V_2",
                "aspect_ratio": "ASPECT_9_16",
            }
        }
        resp = requests.post(
            "https://api.ideogram.ai/generate",
            headers=headers, json=payload, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("data", [])
        if not images:
            raise RuntimeError("Ideogram: no images returned")
        img_url = images[0].get("url", "")
        if not img_url:
            raise RuntimeError("Ideogram: no image URL")
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Ideogram: failed to download image")

    def _try_leonardo(self, prompt: str) -> bytes:
        """Try Leonardo AI API (excellent quality, $5 free credit)."""
        from config import get_leonardo_api_key
        api_key = get_leonardo_api_key()
        if not api_key:
            raise RuntimeError("Leonardo AI API key not configured")

        print(colored(f"    [Leonardo AI] Generating...", "cyan"), flush=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:1000],
            "modelId": "b24e16ff-06e3-43eb-8d33-4416c2d75876",  # Leonardo Lightning XL
            "width": 576,
            "height": 1024,
            "num_images": 1,
        }
        resp = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise RuntimeError("Leonardo: no generation ID returned")

        # Poll for completion
        for _ in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
                headers=headers, timeout=15,
            )
            status_resp.raise_for_status()
            gen = status_resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url", "")
                    img_resp = requests.get(img_url, timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        print(colored("OK", "green"))
                        return img_resp.content
                raise RuntimeError("Leonardo: no image in result")
            elif status == "FAILED":
                raise RuntimeError("Leonardo: generation failed")
        raise RuntimeError("Leonardo: timeout waiting for generation")

    def _extract_search_query(self, prompt: str) -> str:
        """Extract clean search keywords from an AI image prompt for stock photo search."""
        import re
        # Remove common AI style/photography keywords
        style_words = r'\b(cinematic|dramatic|lighting|8K|4K|ultra|HD|macro|bokeh|aerial|drone|cyberpunk|hyper-realistic|vibrant|saturated|documentary|photography|shot|wide|close-up|extreme|detailed|textures?|colors?|film grain|neon|volumetric|fog|aesthetic|digital painting|golden hour|breathtaking|raw|authentic|feel|shallow depth|field|sweeping|portrait|style|composition|render|realistic|illustration|art|scene|view|high quality|resolution|background|foreground|angle|perspective|moody|atmosphere|accent|dark|light)\b'
        cleaned = re.sub(style_words, '', prompt, flags=re.IGNORECASE)
        cleaned = re.sub(r'[,\-:;"\'\(\)]', ' ', cleaned)
        cleaned = ' '.join(cleaned.split())
        # Take meaningful words (3-6) for search
        words = [w for w in cleaned.split() if len(w) > 2][:6]
        query = ' '.join(words) if words else self.subject
        return query

    def _try_pexels(self, prompt: str) -> bytes:
        """Try Pexels stock photos API (free, reliable, HD). Requires free API key."""
        from config import get_pexels_api_key
        api_key = get_pexels_api_key()
        if not api_key:
            raise RuntimeError("Pexels API key not configured")

        import urllib.parse
        import random
        query = self._extract_search_query(prompt)
        print(colored(f"    [Pexels] Searching: {query[:50]}...", "cyan"), flush=True)
        headers = {"Authorization": api_key}
        # Fetch more results and pick a random page for more variety
        page = random.randint(1, 3)
        resp = requests.get(
            f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=15&page={page}",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            raise RuntimeError("Pexels: no photos found")

        # Filter out already-used images
        available = [p for p in photos if p["src"]["large2x"] not in self._used_stock_urls]
        if not available:
            available = photos  # all used, allow repeats as last resort

        photo = random.choice(available)
        img_url = photo["src"]["large2x"]  # high-res version
        self._used_stock_urls.add(img_url)
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Pexels: failed to download image")

    def _try_pixabay(self, prompt: str) -> bytes:
        """Try Pixabay stock photos API (free, reliable, HD). Requires free API key."""
        from config import get_pixabay_api_key
        api_key = get_pixabay_api_key()
        if not api_key:
            raise RuntimeError("Pixabay API key not configured")

        import urllib.parse
        import random
        query = self._extract_search_query(prompt)
        print(colored(f"    [Pixabay] Searching: {query[:50]}...", "cyan"), flush=True)
        page = random.randint(1, 3)
        resp = requests.get(
            f"https://pixabay.com/api/?key={api_key}&q={urllib.parse.quote(query)}&image_type=photo&per_page=15&page={page}&min_width=1080",
            timeout=30,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            raise RuntimeError("Pixabay: no photos found")

        # Filter out already-used images
        available = [h for h in hits if h.get("largeImageURL", "") not in self._used_stock_urls]
        if not available:
            available = hits

        hit = random.choice(available)
        img_url = hit.get("largeImageURL", hit.get("webformatURL", ""))
        if not img_url:
            raise RuntimeError("Pixabay: no image URL in result")
        self._used_stock_urls.add(img_url)
        img_resp = requests.get(img_url, timeout=60)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            print(colored("OK", "green"))
            return img_resp.content
        raise RuntimeError("Pixabay: failed to download image")

    def _try_picsum_stock(self, prompt: str) -> bytes:
        """Fallback: HD stock photo from Picsum (fast, always works)."""
        print(colored(f"    [Picsum HD] Getting image...", "yellow"), flush=True)
        seed = abs(hash(prompt)) % 1000
        url = f"https://picsum.photos/seed/{seed}/1080/1920"
        resp = requests.get(url, timeout=60, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Picsum returned status {resp.status_code}")

    def _generate_fallback_image(self, prompt: str) -> str:
        """
        Generates a stylish fallback image using Pillow when all API providers fail.
        """
        from PIL import Image, ImageDraw, ImageFont
        import random as rand_mod

        if get_verbose():
            warning("All providers failed. Creating styled fallback image...")

        # Create gradient background
        color_schemes = [
            ((15, 15, 80), (80, 20, 120)),
            ((10, 50, 80), (20, 100, 100)),
            ((60, 10, 60), (120, 30, 80)),
            ((10, 40, 20), (30, 100, 60)),
        ]
        c1, c2 = rand_mod.choice(color_schemes)
        img = Image.new("RGB", (1080, 1920))
        draw = ImageDraw.Draw(img)

        for y in range(1920):
            r = int(c1[0] + (c2[0] - c1[0]) * y / 1920)
            g = int(c1[1] + (c2[1] - c1[1]) * y / 1920)
            b = int(c1[2] + (c2[2] - c1[2]) * y / 1920)
            draw.line([(0, y), (1080, y)], fill=(r, g, b))

        # Add text
        try:
            font_path = os.path.join(get_fonts_dir(), get_font())
            font = ImageFont.truetype(font_path, 52)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        lines, current_line = [], ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) > 25:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines.append(current_line)

        y_pos = 1920 // 2 - (len(lines) * 70) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            # Shadow
            draw.text(((1080 - w) // 2 + 3, y_pos + 3), line, fill=(0, 0, 0), font=font)
            # Text
            draw.text(((1080 - w) // 2, y_pos), line, fill="white", font=font)
            y_pos += 70

        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        img.save(image_path)
        self.images.append(image_path)

        if get_verbose():
            info(f' => Wrote fallback image to "{image_path}"')

        return image_path

    def generate_images_batch(self, prompts: List[str]) -> None:
        """
        Generate ALL images using multiple providers in cascade.
        Pollinations FLUX → Pollinations turbo → Pollinations flux-realism → HuggingFace → Pillow fallback.
        """
        print(colored(f"\n  [Images] Generating {len(prompts)} images...", "blue"))

        for i, prompt in enumerate(prompts):
            print(colored(f"\n  Image {i+1}/{len(prompts)}", "blue"))
            saved = False
            for name, fn in [
                # Tier 1: High-quality AI generator
                ("Leonardo AI", self._try_leonardo),
                # Tier 2: Free unlimited AI generators (no daily limits)
                ("Pollinations FLUX", self._try_pollinations),
                ("Pollinations turbo", self._try_pollinations_turbo),
                ("Pollinations flux-realism", self._try_pollinations_realism),
                ("HuggingFace", self._try_huggingface),
                # Tier 3: Stock photos (reliable, always available)
                ("Pexels", self._try_pexels),
                ("Pixabay", self._try_pixabay),
            ]:
                try:
                    img_bytes = fn(prompt)
                    if img_bytes and len(img_bytes) > 1000:
                        self._persist_image(img_bytes, name)
                        saved = True
                        break
                except Exception as e:
                    if get_verbose():
                        warning(f"    {name} failed: {str(e)[:100]}")
                    time.sleep(1)
            if not saved:
                self._generate_fallback_image(prompt)

        success(f"All {len(prompts)} images ready!")

    def generate_image(self, prompt: str) -> str:
        """
        Generates an AI Image trying multiple FREE providers in cascade:
        1. HuggingFace (new router URL, needs free token)
        2. Pollinations.ai (free, no key — currently unstable)
        3. AI Horde (free, no key — crowdsourced SD, ~60-90s)
        4. Picsum (HD stock photos, fast)
        5. Pillow gradient fallback

        Args:
            prompt (str): Reference for image generation

        Returns:
            path (str): The path to the generated image.
        """
        providers = [
            ("Pollinations FLUX", self._try_pollinations),
            ("Pollinations turbo", self._try_pollinations_turbo),
            ("Pollinations flux-realism", self._try_pollinations_realism),
            ("HuggingFace", self._try_huggingface),
        ]

        print(colored(f"  [Image] {prompt[:80]}...", "blue"))

        for name, provider_fn in providers:
            try:
                img_bytes = provider_fn(prompt)
                if img_bytes and len(img_bytes) > 1000:
                    success(f"Image generated via {name}!")
                    return self._persist_image(img_bytes, name)
            except Exception as e:
                if get_verbose():
                    warning(f"{name} failed: {str(e)[:100]}")
                time.sleep(1)

        # All providers failed - use Pillow fallback
        return self._generate_fallback_image(prompt)

    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        """
        Converts the generated script into Speech and returns the path to the wav file.
        Also captures word-level timestamps for karaoke subtitles when available.

        Args:
            tts_instance (tts): Instance of TTS Class.

        Returns:
            path_to_wav (str): Path to generated audio (WAV Format).
        """
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Clean script
        self.script = re.sub(r"[^\w\s.?!]", "", self.script)

        path, word_timestamps = tts_instance.synthesize_with_timestamps(self.script, path)
        self.word_timestamps = word_timestamps

        self.tts_path = path

        if get_verbose():
            ts_info = f" ({len(word_timestamps)} words timed)" if word_timestamps else ""
            info(f' => Wrote TTS to "{path}"{ts_info}')

        return path

    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        videos = self.get_videos()
        videos.append(video)

        cache = get_youtube_cache_path()

        with open(cache, "r", encoding="utf-8") as file:
            previous_json = json.loads(file.read())

            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    account["videos"].append(video)

            # Commit changes
            with open(cache, "w", encoding="utf-8") as f:
                f.write(json.dumps(previous_json))

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles from the known script text.
        Uses script-based generation by default (instant, no STT needed since we
        already have the exact text). Falls back to STT only if explicitly configured.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "script").lower()

        # Default: use the script we already have (instant, no extra dependencies)
        if provider not in ("local_whisper", "third_party_assemblyai"):
            return self.generate_subtitles_from_script(audio_path)

        try:
            if provider == "local_whisper":
                return self.generate_subtitles_local_whisper(audio_path)

            if provider == "third_party_assemblyai":
                return self.generate_subtitles_assemblyai(audio_path)
        except Exception as e:
            warning(f"STT subtitles failed ({e}), using script-based subtitles instead.")

        return self.generate_subtitles_from_script(audio_path)

    def generate_subtitles_from_script(self, audio_path: str) -> str:
        """
        Generates subtitles by splitting the script text into sentences
        and distributing them evenly across the audio duration.
        No STT engine required.

        Args:
            audio_path (str): Audio file path (used to get duration)

        Returns:
            path (str): Path to SRT file
        """
        from moviepy.editor import AudioFileClip as _AFC

        duration = _AFC(audio_path).duration
        sentences = re.split(r'(?<=[.!?])\s+', self.script.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            sentences = [self.script.strip()]

        seg_dur = duration / len(sentences)
        lines = []

        for idx, sentence in enumerate(sentences):
            start = self._format_srt_timestamp(idx * seg_dur)
            end = self._format_srt_timestamp(min((idx + 1) * seg_dur, duration))
            lines.append(str(idx + 1))
            lines.append(f"{start} --> {end}")
            lines.append(sentence)
            lines.append("")

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))

        if get_verbose():
            info(f" => Generated script-based subtitles ({len(sentences)} segments)")

        return srt_path

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig()
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")

        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        whisper_model_name = get_whisper_model()
        print(colored(f"  [Whisper] Loading model '{whisper_model_name}'...", "cyan"), flush=True)
        model = WhisperModel(
            whisper_model_name,
            device=get_whisper_device(),
            compute_type=get_whisper_compute_type(),
        )
        print(colored(f"  [Whisper] Transcribing audio...", "cyan"), flush=True)
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        lines = []
        for idx, segment in enumerate(segments, start=1):
            start = self._format_srt_timestamp(segment.start)
            end = self._format_srt_timestamp(segment.end)
            text = str(segment.text).strip()

            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        subtitles = "\n".join(lines)
        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def _build_karaoke_subtitles(self, audio_duration: float):
        """
        Build word-by-word karaoke subtitle clip from word_timestamps.
        Shows groups of up to 5 words with multi-line wrapping; the active
        word is highlighted in yellow — modern YouTube Shorts style.
        """
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        words = self.word_timestamps
        if not words:
            return None

        font_path = os.path.join(get_fonts_dir(), "Poppins-Black.ttf").replace("\\", "/")
        font_size = 80
        font = ImageFont.truetype(font_path, font_size)
        canvas_w = 1080
        max_line_width = 920
        word_spacing = 28
        line_spacing = 0  # ascent+descent already provides natural spacing
        max_words_per_group = 5
        max_lines = 3

        # Measure height of a single line using full font metrics (ascent + descent)
        # plus stroke so descenders (g, y, p) and strokes never get clipped
        ascent, descent = font.getmetrics()
        line_h = ascent + descent

        # --- Helper: wrap a list of texts into lines that fit max_line_width ---
        def _wrap_group(texts):
            """Returns list of lines, each line is a list of (text, width) tuples."""
            lines = []
            current_line = []
            current_w = 0
            for t in texts:
                bb = font.getbbox(t)
                tw = bb[2] - bb[0]
                test_w = current_w + tw + (word_spacing if current_line else 0)
                if current_line and test_w > max_line_width:
                    lines.append(current_line)
                    current_line = [(t, tw)]
                    current_w = tw
                else:
                    current_line.append((t, tw))
                    current_w = test_w
            if current_line:
                lines.append(current_line)
            return lines

        # --- Group words (up to 5, but never exceeding max_lines when wrapped) ---
        groups = []
        current_group = []

        for w in words:
            candidate = current_group + [w]
            candidate_texts = [gw["word"].upper() for gw in candidate]
            lines_needed = len(_wrap_group(candidate_texts))
            if len(candidate) > max_words_per_group or lines_needed > max_lines:
                if current_group:
                    groups.append(current_group)
                current_group = [w]
            else:
                current_group = candidate
        if current_group:
            groups.append(current_group)

        # --- Build index: global word index → (group_idx, local_idx) ---
        word_to_group = {}
        gi = 0
        for g_idx, group in enumerate(groups):
            for l_idx in range(len(group)):
                word_to_group[gi] = (g_idx, l_idx)
                gi += 1

        # --- Pre-render one frame per word (group with that word highlighted) ---
        # First pass: determine max canvas height across all groups
        max_num_lines = 1
        for group in groups:
            texts = [gw["word"].upper() for gw in group]
            lines = _wrap_group(texts)
            max_num_lines = max(max_num_lines, len(lines))

        stroke_pad = 6 * 2  # stroke_width extends outward on all sides
        canvas_h = max_num_lines * line_h + (max_num_lines - 1) * line_spacing + stroke_pad + 20

        rendered = {}  # global_word_idx → (rgb np.array, alpha np.array)

        for word_idx, (g_idx, l_idx) in word_to_group.items():
            group = groups[g_idx]
            texts = [gw["word"].upper() for gw in group]
            lines = _wrap_group(texts)

            img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Track which global-in-group index we're drawing
            word_counter = 0
            y = 20
            for line in lines:
                line_total_w = sum(tw for _, tw in line) + word_spacing * (len(line) - 1)
                x = (canvas_w - line_total_w) // 2
                for t, tw in line:
                    if word_counter == l_idx:
                        draw.text((x, y), t, fill=(255, 215, 0), font=font,
                                  stroke_width=6, stroke_fill="black")
                    else:
                        draw.text((x, y), t, fill="white", font=font,
                                  stroke_width=6, stroke_fill="black")
                    x += tw + word_spacing
                    word_counter += 1
                y += line_h + line_spacing

            arr = np.array(img)
            rendered[word_idx] = (arr[:, :, :3], arr[:, :, 3].astype(np.float64) / 255.0)

        # Blank frame for silence gaps
        blank_rgb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        blank_alpha = np.zeros((canvas_h, canvas_w), dtype=np.float64)

        # --- Lookup: find active word at time t ---
        def find_active(t):
            for i, w in enumerate(words):
                if w["start"] <= t <= w["end"]:
                    return i
            # Between words: keep showing the last spoken word
            for i in range(len(words) - 1):
                if words[i]["end"] < t < words[i + 1]["start"]:
                    return i
            if words and t >= words[-1]["start"]:
                return len(words) - 1
            return -1

        def make_rgb(t):
            idx = find_active(t)
            if idx < 0 or idx not in rendered:
                return blank_rgb
            return rendered[idx][0]

        def make_mask(t):
            idx = find_active(t)
            if idx < 0 or idx not in rendered:
                return blank_alpha
            return rendered[idx][1]

        clip = VideoClip(make_rgb, duration=audio_duration).set_fps(30)
        mask = VideoClip(make_mask, duration=audio_duration, ismask=True).set_fps(30)
        clip = clip.set_mask(mask)
        clip = clip.set_position(("center", 1300))
        return clip

    def _estimate_word_timestamps(self, audio_duration: float):
        """Estimate word timestamps from script when TTS didn't provide them."""
        words = self.script.split()
        if not words:
            return []
        dur_per_word = audio_duration / len(words)
        return [
            {"start": i * dur_per_word, "end": (i + 1) * dur_per_word, "word": w}
            for i, w in enumerate(words)
        ]

    def combine(self) -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        req_dur = max_duration / len(self.images)

        print(colored("[+] Combining images...", "blue"))

        # Verify all images exist
        valid_images = [p for p in self.images if os.path.exists(p)]
        if not valid_images:
            raise FileNotFoundError("No valid images found for video combination")
        if len(valid_images) != len(self.images):
            missing = [p for p in self.images if not os.path.exists(p)]
            if get_verbose():
                warning(f"Missing {len(missing)} images, using {len(valid_images)} valid ones")
            self.images = valid_images

        clips = []
        tot_dur = 0
        # Add each image once, distributing duration evenly
        for idx, image_path in enumerate(self.images):
            if tot_dur >= max_duration:
                break
            # Last clip gets remaining duration to avoid float mismatch
            if idx == len(self.images) - 1:
                this_dur = max_duration - tot_dur
            else:
                this_dur = req_dur
            clip = ImageClip(image_path)
            clip.duration = this_dur
            clip = clip.set_fps(30)

            # Not all images are same size,
            # so we need to resize them
            if round((clip.w / clip.h), 4) < 0.5625:
                if get_verbose():
                    info(f" => Resizing Image: {image_path} to 1080x1920")
                clip = crop(
                    clip,
                    width=clip.w,
                    height=round(clip.w / 0.5625),
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                )
            else:
                if get_verbose():
                    info(f" => Resizing Image: {image_path} to 1920x1080")
                clip = crop(
                    clip,
                    width=round(0.5625 * clip.h),
                    height=clip.h,
                    x_center=clip.w / 2,
                    y_center=clip.h / 2,
                )
            clip = clip.resize((1080, 1920))

            clips.append(clip)
            tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips)
        final_clip = final_clip.set_fps(30)
        random_song = choose_random_song()

        subtitles = None
        try:
            print(colored("[+] Building karaoke subtitles...", "blue"), flush=True)

            # If TTS didn't provide word timestamps, estimate them
            if not self.word_timestamps:
                self.word_timestamps = self._estimate_word_timestamps(max_duration)

            subtitles = self._build_karaoke_subtitles(max_duration)

            if subtitles is not None:
                print(colored("[+] Karaoke subtitles ready.", "green"), flush=True)
        except Exception as e:
            warning(f"Failed to generate subtitles, continuing without subtitles: {e}")

        print(colored("[+] Mixing audio...", "blue"), flush=True)
        random_song_clip = AudioFileClip(random_song).set_fps(44100)

        # Loop background music if shorter than TTS, then trim to match
        if random_song_clip.duration < tts_clip.duration:
            loops_needed = int(tts_clip.duration // random_song_clip.duration) + 1
            random_song_clip = concatenate_audioclips([random_song_clip] * loops_needed)
        random_song_clip = random_song_clip.subclip(0, tts_clip.duration)

        # Background music at 15% volume (audible but won't overpower voice)
        random_song_clip = random_song_clip.fx(afx.volumex, 0.15)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        final_clip = final_clip.set_audio(comp_audio)
        # Don't force set_duration — clips already sum to max_duration exactly

        if subtitles is not None:
            final_clip = CompositeVideoClip([final_clip, subtitles])

        print(colored("[+] Rendering final video (this may take a minute)...", "blue"), flush=True)
        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS) -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Args:
            tts_instance (TTS): Instance of TTS Class.

        Returns:
            path (str): The path to the generated MP4 File, or empty string if cancelled.
        """
        # Generate the Topic
        self.generate_topic()

        # Generate the Script
        self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts
        self.generate_prompts()

        # Generate the Images (parallel batch for speed)
        self.generate_images_batch(self.image_prompts)

        # Generate the TTS
        self.generate_script_to_speech(tts_instance)

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)

        return path

    # ============================================================
    #  LONG VIDEO PIPELINE (5-10 minutes, 16:9 landscape)
    # ============================================================

    def generate_long_script(self) -> str:
        """
        Generates a structured long-form script with chapters for a 5-10 minute video.
        The script is split into: hook, 4-5 body sections, and a closing.
        """
        prompt = f"""You are an expert documentary narrator and scriptwriter.
Write a compelling 5-to-7-minute narration script about the following topic.

Topic: {self.subject}

STRUCTURE (use these exact section markers):
[INTRO]
A powerful opening hook (2-3 sentences). Start with a mind-blowing fact, a provocative question, or a bold claim that instantly grabs attention.

[SECTION 1: <title>]
First main point (4-5 sentences). Dive deep into the first fascinating aspect of the topic.

[SECTION 2: <title>]
Second main point (4-5 sentences). Explore a different angle or build on the previous section.

[SECTION 3: <title>]
Third main point (4-5 sentences). Reveal surprising connections or lesser-known facts.

[SECTION 4: <title>]
Fourth main point (4-5 sentences). The climax — the most mind-blowing part of the topic.

[CLOSING]
A memorable conclusion (2-3 sentences). End with a thought-provoking reflection that stays with the viewer.

STYLE RULES:
- Write like a passionate storyteller, NOT a textbook. Use vivid, sensory language.
- Each sentence should flow naturally into the next, as if spoken aloud.
- Use rhetorical questions, surprising comparisons, and emotional hooks.
- Keep sentences SHORT and punchy (under 20 words each).
- Total script should be approximately 800-1200 words (5-7 minutes when spoken).
- WRITE ENTIRELY IN {self.language}. Every single word must be in {self.language}.
- DO NOT include any stage directions, speaker labels, or meta-text.
- DO NOT use markdown formatting, bullet points, or numbered lists.
- ONLY return the script with the section markers as shown above.
"""
        completion = self.generate_response(prompt)
        completion = re.sub(r"\*", "", completion)

        if not completion or len(completion) < 200:
            error("Long script generation failed or too short.")
            raise RuntimeError("Failed to generate long script")

        self.script = completion

        if get_verbose():
            word_count = len(completion.split())
            info(f" => Generated long script: {word_count} words")

        return completion

    def generate_long_metadata(self) -> dict:
        """
        Generates metadata optimized for long-form YouTube videos.
        """
        title = self.generate_response(
            f"Generate a compelling YouTube video title for this topic: {self.subject}. "
            f"Make it intriguing and click-worthy but NOT clickbait. Optionally include 1-2 relevant hashtags at the end (only if they fit naturally). "
            f"Keep it under 80 characters. Only return the title. "
            f"Do NOT wrap the title in quotes. Do NOT start or end with any quote character. "
            f"YOU MUST WRITE IN {self.language}."
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        title = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', title.strip()).strip()

        if len(title) > 100:
            if "#" in title:
                title = title[:title.index("#")].strip()
            if len(title) > 100:
                title = title[:100]

        description = self.generate_response(
            f"""Generate a YouTube video description for a long-form video with this script:

{self.script[:2000]}

Include:
- A brief 2-sentence summary of the video
- 5-8 relevant hashtags
- A call to action (subscribe, like, comment)

Do NOT wrap the description in quotes. Do NOT start or end with any quote character.
Write entirely in {self.language}. Only return the description."""
        )

        # Strip any quotes the LLM might add (regular, curly, single)
        description = re.sub(r'^[\"\'\u201c\u201d\u2018\u2019]+|[\"\'\u201c\u201d\u2018\u2019]+$', '', description.strip()).strip()

        self.metadata = {"title": title, "description": description}
        return self.metadata

    def generate_long_prompts(self) -> List[str]:
        """
        Generates 15-18 image prompts for a long video, covering each section of the script.
        """
        n_prompts = 16

        prompt = f"""Generate exactly {n_prompts} Image Prompts for AI Image Generation.

This is for a long-form documentary-style video. The images will be shown in 16:9 landscape format.

Script:
{self.script[:3000]}

RULES:
- Generate EXACTLY {n_prompts} prompts, distributed across ALL sections of the script.
- Each prompt must illustrate a SPECIFIC moment or concept from the script.
- Be CONCRETE: describe exactly what appears (objects, people, setting, lighting, colors, textures, composition).
- NEVER use abstract words like "visualization", "concept", "essence", "metaphor".
- Each prompt MUST specify a DIFFERENT cinematic style. Rotate through these:
  * "cinematic wide shot, dramatic lighting, film grain, 8K ultra HD, 16:9 landscape"
  * "extreme close-up, shallow depth of field, bokeh, macro detail"
  * "aerial establishing shot, sweeping vista, golden hour, epic scale"
  * "dark atmospheric scene, volumetric lighting, moody shadows"
  * "hyper-realistic CGI render, vivid colors, detailed textures, studio lighting"
  * "documentary photography, natural light, authentic feel, photojournalistic"
  * "space/cosmic visualization, deep field, stars, nebula, astronomical"
  * "microscopic or scientific imagery, detailed cross-section, educational diagram style"
- Each prompt should be 40-80 words describing the full scene.
- Write prompts in English for best image generation quality.

Return ONLY a JSON array of {n_prompts} strings. No markdown, no explanation."""

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        image_prompts = []
        try:
            parsed = json.loads(completion)
            if isinstance(parsed, list):
                image_prompts = [str(p) for p in parsed if isinstance(p, str)]
        except Exception:
            match = re.search(r'\[.*\]', completion, re.DOTALL)
            if match:
                try:
                    image_prompts = json.loads(match.group())
                except Exception:
                    pass

        if not image_prompts or len(image_prompts) < 4:
            if get_verbose():
                warning("Failed to parse long video prompts, using fallback")
            image_prompts = [
                f"{self.subject}, cinematic wide shot, dramatic lighting, 8K, landscape",
                f"{self.subject}, extreme close-up detail, shallow depth of field, bokeh",
                f"{self.subject}, aerial drone view, golden hour, sweeping landscape",
                f"{self.subject}, dark moody atmosphere, volumetric fog, neon accents",
                f"{self.subject}, hyper-realistic CGI, vivid saturated colors, studio lighting",
                f"{self.subject}, documentary photography, natural light, raw authentic",
                f"{self.subject}, cosmic space visualization, deep field stars, nebula",
                f"{self.subject}, scientific microscopic imagery, detailed cross-section",
                f"{self.subject}, cinematic panorama, film grain, dramatic sky, 8K",
                f"{self.subject}, intimate portrait shot, rim lighting, emotional",
                f"{self.subject}, futuristic technology visualization, holographic, blue tones",
                f"{self.subject}, underwater or fluid dynamics, bioluminescent, ethereal",
                f"{self.subject}, ancient historical scene, warm tones, detailed architecture",
                f"{self.subject}, abstract geometric patterns, fractal, mathematical beauty",
                f"{self.subject}, sunset silhouette, dramatic contrast, wide angle",
                f"{self.subject}, time-lapse style, motion blur, dynamic energy, vivid",
            ]

        image_prompts = image_prompts[:n_prompts]
        self.image_prompts = image_prompts

        if get_verbose():
            info(f" => Generated {len(image_prompts)} long video image prompts")

        return image_prompts

    def _try_leonardo_landscape(self, prompt: str) -> bytes:
        """Try Leonardo AI API in 16:9 landscape format for long videos."""
        from config import get_leonardo_api_key
        api_key = get_leonardo_api_key()
        if not api_key:
            raise RuntimeError("Leonardo AI API key not configured")

        print(colored(f"    [Leonardo AI 16:9] Generating...", "cyan"), flush=True)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt[:1000],
            "modelId": "b24e16ff-06e3-43eb-8d33-4416c2d75876",  # Leonardo Lightning XL
            "width": 1024,
            "height": 576,
            "num_images": 1,
        }
        resp = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/generations",
            headers=headers, json=payload, timeout=30,
        )
        resp.raise_for_status()
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise RuntimeError("Leonardo: no generation ID returned")

        for _ in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
                headers=headers, timeout=15,
            )
            status_resp.raise_for_status()
            gen = status_resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url", "")
                    img_resp = requests.get(img_url, timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        print(colored("OK", "green"))
                        return img_resp.content
                raise RuntimeError("Leonardo: no image in result")
            elif status == "FAILED":
                raise RuntimeError("Leonardo: generation failed")
        raise RuntimeError("Leonardo: timeout waiting for generation")

    def generate_long_images(self, prompts: List[str]) -> None:
        """
        Generate images for long video in 16:9 landscape format (1920x1080).
        Cascade: Leonardo AI → Pollinations FLUX → HuggingFace → Pillow fallback.
        """
        print(colored(f"\n  [Long Video] Generating {len(prompts)} images (1920x1080)...", "blue"))

        for i, prompt in enumerate(prompts):
            print(colored(f"\n  Image {i+1}/{len(prompts)}", "blue"))
            saved = False

            for name, fn in [
                ("Leonardo AI", lambda p: self._try_leonardo_landscape(p)),
                ("Pollinations.ai FLUX", lambda p: self._try_pollinations_landscape(p)),
                ("HuggingFace", self._try_huggingface),
            ]:
                try:
                    img_bytes = fn(prompt)
                    if img_bytes and len(img_bytes) > 1000:
                        self._persist_image(img_bytes, name)
                        saved = True
                        break
                except Exception as e:
                    if get_verbose():
                        warning(f"    {name} failed: {str(e)[:100]}")
                    time.sleep(1)

            if not saved:
                self._generate_fallback_image_landscape(prompt)

        success(f"All {len(self.images)} long video images ready!")

    def _try_pollinations_landscape(self, prompt: str) -> bytes:
        """Pollinations.ai in 16:9 landscape for long videos."""
        import urllib.parse
        encoded = urllib.parse.quote(prompt[:500])
        seed = int(time.time())
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080&nologo=true&seed={seed}&model=flux"
        print(colored(f"    [Pollinations FLUX 16:9] Generating...", "cyan"), flush=True)
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200 and len(resp.content) > 5000:
            print(colored("OK", "green"))
            return resp.content
        raise RuntimeError(f"Pollinations returned status {resp.status_code}")

    def _generate_fallback_image_landscape(self, prompt: str) -> str:
        """Fallback landscape image (1920x1080) when all providers fail."""
        from PIL import Image, ImageDraw, ImageFont
        import random as rand_mod

        if get_verbose():
            warning("All providers failed. Creating styled fallback image (landscape)...")

        color_schemes = [
            ((15, 15, 80), (80, 20, 120)),
            ((10, 50, 80), (20, 100, 100)),
            ((60, 10, 60), (120, 30, 80)),
            ((10, 40, 20), (30, 100, 60)),
        ]
        c1, c2 = rand_mod.choice(color_schemes)
        img = Image.new("RGB", (1920, 1080))
        draw = ImageDraw.Draw(img)

        for y in range(1080):
            r = int(c1[0] + (c2[0] - c1[0]) * y / 1080)
            g = int(c1[1] + (c2[1] - c1[1]) * y / 1080)
            b = int(c1[2] + (c2[2] - c1[2]) * y / 1080)
            draw.line([(0, y), (1920, y)], fill=(r, g, b))

        try:
            font_path = os.path.join(get_fonts_dir(), get_font())
            font = ImageFont.truetype(font_path, 48)
        except Exception:
            font = ImageFont.load_default()

        words = prompt.split()
        text_lines, current_line = [], ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) > 45:
                text_lines.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            text_lines.append(current_line)

        y_pos = 1080 // 2 - (len(text_lines) * 60) // 2
        for line in text_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            draw.text(((1920 - w) // 2 + 3, y_pos + 3), line, fill=(0, 0, 0), font=font)
            draw.text(((1920 - w) // 2, y_pos), line, fill="white", font=font)
            y_pos += 60

        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
        img.save(image_path)
        self.images.append(image_path)
        return image_path

    def combine_long(self) -> str:
        """
        Combines images and audio into a long-form 16:9 landscape video.
        No subtitles, cinematic Ken Burns effect (slow zoom/pan), smooth transitions.
        """
        combined_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        req_dur = max_duration / len(self.images)

        print(colored(f"[+] Combining {len(self.images)} images into long video ({max_duration:.0f}s)...", "blue"))

        valid_images = [p for p in self.images if os.path.exists(p)]
        if not valid_images:
            raise FileNotFoundError("No valid images found")
        self.images = valid_images

        clips = []
        tot_dur = 0

        while tot_dur < max_duration:
            for image_path in self.images:
                if tot_dur >= max_duration:
                    break

                clip_dur = min(req_dur, max_duration - tot_dur)
                if clip_dur < 0.5:
                    break

                try:
                    img_clip = ImageClip(image_path).set_duration(clip_dur)

                    # Resize to 1920x1080 with proper cropping
                    w, h = img_clip.size
                    aspect = w / h
                    target_aspect = 1920 / 1080

                    if aspect > target_aspect:
                        # Image is wider — scale by height, crop width
                        img_clip = img_clip.resize(height=1080)
                        img_clip = crop(img_clip, x_center=img_clip.w / 2, y_center=540, width=1920, height=1080)
                    else:
                        # Image is taller — scale by width, crop height
                        img_clip = img_clip.resize(width=1920)
                        img_clip = crop(img_clip, x_center=960, y_center=img_clip.h / 2, width=1920, height=1080)

                    img_clip = img_clip.set_fps(30)

                    # Ken Burns effect: slow zoom in (1.0x to 1.10x)
                    # Uses resize() which is much faster than per-frame numpy ops
                    img_clip = img_clip.resize(lambda t: 1 + 0.10 * (t / clip_dur))

                    # Crossfade: fade in first 0.5s, fade out last 0.5s
                    if clip_dur > 1.5:
                        img_clip = img_clip.crossfadein(0.5).crossfadeout(0.5)

                    clips.append(img_clip)
                    tot_dur += clip_dur

                except Exception as e:
                    if get_verbose():
                        warning(f"Skipping image {image_path}: {e}")
                    continue

        if not clips:
            raise RuntimeError("No clips could be created from images")

        # Concatenate with crossfade transitions
        print(colored("[+] Applying transitions...", "blue"), flush=True)
        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip = final_clip.set_fps(30)

        # Audio: TTS + background music
        print(colored("[+] Mixing audio...", "blue"), flush=True)
        random_song = choose_random_song()
        music_clip = AudioFileClip(random_song).set_fps(44100)

        # Loop music if shorter than TTS
        if music_clip.duration < tts_clip.duration:
            loops_needed = int(tts_clip.duration // music_clip.duration) + 1
            music_clip = concatenate_audioclips([music_clip] * loops_needed)
        music_clip = music_clip.subclip(0, tts_clip.duration)

        # Background music at 10% volume for long videos (subtle ambient)
        music_clip = music_clip.fx(afx.volumex, 0.10)

        # Fade in music at start, fade out at end
        music_clip = music_clip.audio_fadein(3.0).audio_fadeout(3.0)

        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), music_clip])

        final_clip = final_clip.set_audio(comp_audio)
        final_clip = final_clip.set_duration(tts_clip.duration)

        print(colored("[+] Rendering long video (this may take several minutes)...", "blue"), flush=True)
        final_clip.write_videofile(
            combined_path,
            threads=threads,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
        )

        success(f'Wrote long video to "{combined_path}"')
        return combined_path

    def generate_long_video(self, tts_instance: TTS) -> str:
        """
        Full pipeline for generating a long-form YouTube video (5-10 minutes).
        16:9 landscape, documentary style, no subtitles.

        Args:
            tts_instance (TTS): Instance of TTS Class.

        Returns:
            path (str): Path to the generated MP4 file.
        """
        info("=" * 50)
        info("  LONG VIDEO GENERATION PIPELINE")
        info("=" * 50)

        # Step 1: Generate Topic
        info("\n[1/6] Generating topic...")
        self.generate_topic()
        success(f" Topic: {self.subject}")

        # Step 2: Generate long script with chapters
        info("\n[2/6] Generating long-form script...")
        self.generate_long_script()

        # Step 3: Generate metadata
        info("\n[3/6] Generating title & description...")
        self.generate_long_metadata()
        success(f" Title: {self.metadata['title']}")

        # Step 4: Generate image prompts
        info("\n[4/6] Generating image prompts...")
        self.images = []  # Reset images
        self.generate_long_prompts()

        # Step 5: Generate images (landscape 1920x1080)
        info("\n[5/6] Generating images...")
        self.generate_long_images(self.image_prompts)

        # Step 6: Generate TTS with natural voice
        info("\n[6/6] Generating narration audio...")
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Clean script of section markers for TTS, keep the text
        tts_script = self.script
        tts_script = re.sub(r'\[INTRO\]', '', tts_script)
        tts_script = re.sub(r'\[SECTION \d+:.*?\]', '', tts_script)
        tts_script = re.sub(r'\[CLOSING\]', '', tts_script)
        tts_script = re.sub(r'\[CIERRE\]', '', tts_script)
        tts_script = re.sub(r'\[SECCIÓN \d+:.*?\]', '', tts_script)
        tts_script = re.sub(r'\[INTRODUCCIÓN\]', '', tts_script)
        tts_script = re.sub(r"[^\w\s.?!,;:'\"-]", "", tts_script)
        tts_script = re.sub(r'\n{3,}', '\n\n', tts_script).strip()

        # Use the long-form TTS with SSML prosody for natural narration
        tts_instance.synthesize_long(tts_script, path, voice_id="es-MX-JorgeNeural")
        self.tts_path = path

        if get_verbose():
            audio_dur = AudioFileClip(path).duration
            info(f" => Audio duration: {audio_dur:.0f} seconds ({audio_dur/60:.1f} min)")

        # Step 7: Combine everything
        info("\n[+] Assembling final video...")
        video_path = self.combine_long()

        self.video_path = os.path.abspath(video_path)
        success(f"\n=> Long video generated: {video_path}")

        return video_path

    def _ensure_browser(self) -> None:
        """
        Ensures the Firefox browser is running and connected.
        Launches (or re-launches) the browser if it is None or the session has died.
        Called lazily just before upload so a browser crash during video generation
        does not discard the finished video.
        """
        session_alive = False
        if self.browser is not None:
            try:
                # A simple property access will raise if the session is dead
                _ = self.browser.current_url
                session_alive = True
            except Exception:
                session_alive = False
                try:
                    self.browser.quit()
                except Exception:
                    pass
                self.browser = None

        if not session_alive:
            info(" => Conectando con Firefox...")
            service = Service(GeckoDriverManager().install())
            self.browser = webdriver.Firefox(service=service, options=self.options)
            success(" => Firefox conectado.")

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube via Selenium.
        Uses explicit waits and robust element selection for YouTube Studio 2025+.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys

        self._ensure_browser()
        driver = self.browser
        verbose = get_verbose()
        wait = WebDriverWait(driver, 30)

        try:
            # Step 1: Get channel ID
            if verbose:
                info("\t=> Getting channel ID...")
            self.get_channel_id()
            if verbose:
                info(f"\t=> Channel ID: {self.channel_id}")

            # Step 2: Navigate to upload page
            if verbose:
                info("\t=> Navigating to upload page...")
            driver.get("https://www.youtube.com/upload")
            time.sleep(3)

            # Step 3: Upload the video file
            if verbose:
                info(f"\t=> Uploading file: {self.video_path}")

            # Find the file input (hidden input inside the upload picker)
            file_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(self.video_path)

            if verbose:
                info("\t=> File selected, waiting for upload dialog...")

            # Wait for the upload dialog to appear (title textbox)
            time.sleep(8)

            # Step 4: Set title
            if verbose:
                info("\t=> Setting title...")

            # YouTube Studio uses contenteditable divs with id="textbox"
            textboxes = wait.until(
                EC.presence_of_all_elements_located((By.ID, YOUTUBE_TEXTBOX_ID))
            )

            if len(textboxes) < 2:
                warning(f"Expected 2+ textboxes, found {len(textboxes)}")

            title_el = textboxes[0]
            # Use JavaScript click to bypass overlay dialogs (dialog-scrim, social-suggestions)
            # that YouTube Studio renders on top of the title field.
            driver.execute_script("arguments[0].scrollIntoView(true);", title_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", title_el)
            time.sleep(0.5)
            title_el.send_keys(Keys.CONTROL + "a")
            time.sleep(0.3)
            title_el.send_keys(Keys.DELETE)
            time.sleep(0.3)

            # Type the new title character by character to avoid issues
            clean_title = self.metadata["title"].replace("\n", " ")[:100]
            title_el.send_keys(clean_title)
            time.sleep(1)

            if verbose:
                info(f"\t=> Title set: {clean_title}")

            # Step 5: Set description
            if verbose:
                info("\t=> Setting description...")

            description_el = textboxes[-1]
            # Use JavaScript click to bypass the "Suggested hashtags" panel
            # that YouTube Studio renders between title and description fields.
            # A normal .click() fails with ElementClickInterceptedException.
            driver.execute_script("arguments[0].scrollIntoView(true);", description_el)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", description_el)
            time.sleep(0.5)
            description_el.send_keys(Keys.CONTROL + "a")
            time.sleep(0.3)
            description_el.send_keys(Keys.DELETE)
            time.sleep(0.3)

            clean_desc = self.metadata["description"].replace("\n", " ")[:5000]
            description_el.send_keys(clean_desc)
            time.sleep(1)

            if verbose:
                info("\t=> Description set")

            # Step 6: Set "Not made for kids"
            if verbose:
                info("\t=> Setting 'not made for kids'...")

            try:
                if not get_is_for_kids():
                    not_for_kids = wait.until(
                        EC.element_to_be_clickable((By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME))
                    )
                    not_for_kids.click()
                else:
                    for_kids = wait.until(
                        EC.element_to_be_clickable((By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME))
                    )
                    for_kids.click()
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set kids option: {e}")

            # Step 7: Click Next 3 times (Details → Video elements → Checks → Visibility)
            for step_num in range(3):
                if verbose:
                    info(f"\t=> Clicking Next (step {step_num + 1}/3)...")
                try:
                    next_btn = wait.until(
                        EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
                    )
                    next_btn.click()
                    time.sleep(2)
                except Exception as e:
                    warning(f"Next button step {step_num + 1} failed: {e}")

            # Step 8: Set visibility to Unlisted (radio button index 2)
            if verbose:
                info("\t=> Setting visibility to Unlisted...")

            time.sleep(2)
            try:
                radio_buttons = driver.find_elements(By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH)
                if len(radio_buttons) >= 3:
                    radio_buttons[2].click()  # 0=Private, 1=Unlisted, 2=Public — but YT may reorder
                elif len(radio_buttons) >= 2:
                    radio_buttons[1].click()  # Try unlisted
                time.sleep(1)
            except Exception as e:
                warning(f"Could not set visibility: {e}")

            # Step 9: Click Done
            if verbose:
                info("\t=> Clicking Done button...")

            try:
                done_btn = wait.until(
                    EC.element_to_be_clickable((By.ID, YOUTUBE_DONE_BUTTON_ID))
                )
                done_btn.click()
            except Exception as e:
                warning(f"Done button failed: {e}")

            # Wait for upload to process
            if verbose:
                info("\t=> Waiting for upload to complete...")
            time.sleep(5)

            # Step 10: Get the video URL
            if verbose:
                info("\t=> Getting video URL...")

            driver.get(
                f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
            )
            time.sleep(3)

            url = None
            try:
                videos = driver.find_elements(By.TAG_NAME, "ytcp-video-row")
                if videos:
                    first_video = videos[0]
                    anchor_tag = first_video.find_element(By.TAG_NAME, "a")
                    href = anchor_tag.get_attribute("href")
                    if verbose:
                        info(f"\t=> Found URL: {href}")
                    video_id = href.split("/")[-2]
                    url = build_url(video_id)
            except Exception as e:
                warning(f"Could not get video URL: {e}")
                url = "https://studio.youtube.com"

            self.uploaded_video_url = url or "unknown"

            success(f" => Uploaded Video: {self.uploaded_video_url}")

            # Save to cache
            self.add_video(
                {
                    "title": self.metadata["title"],
                    "description": self.metadata["description"],
                    "subject": self.subject,
                    "url": self.uploaded_video_url,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            driver.quit()
            return True

        except Exception as e:
            import traceback
            error(f"Upload failed: {e}")
            traceback.print_exc()
            try:
                driver.quit()
            except Exception:
                pass
            return False

    def get_videos(self) -> List[dict]:
        """
        Gets the uploaded videos from the YouTube Channel.

        Returns:
            videos (List[dict]): The uploaded videos.
        """
        if not os.path.exists(get_youtube_cache_path()):
            # Create the cache file
            with open(get_youtube_cache_path(), "w", encoding="utf-8") as file:
                json.dump({"videos": []}, file, indent=4)
            return []

        videos = []
        # Read the cache file
        with open(get_youtube_cache_path(), "r", encoding="utf-8") as file:
            previous_json = json.loads(file.read())
            # Find our account
            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account["videos"]

        return videos
