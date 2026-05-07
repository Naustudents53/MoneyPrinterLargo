"""
MoneyPrinterLargo - YouTube Short Generator (standalone test)
Canal: Mind Glitch | Nicho: Science & Mystery Facts
Voz: Carlos (es-MX) | 100% FREE tools
"""
import sys, os, re, json, time, random, shutil, requests, urllib.parse
sys.path.insert(0, "src")

from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

if not shutil.which("ffmpeg"):
    search = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(search):
        for root, dirs, files in os.walk(search):
            if "ffmpeg.exe" in files:
                os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                break

from config import ROOT_DIR, get_fonts_dir, get_font, get_imagemagick_path
from llm_provider import set_llm_provider, select_model, generate_text
from classes.Tts import TTS
from uuid import uuid4

os.makedirs(".mp", exist_ok=True)
from config import get_llm_provider, get_ollama_model
_provider = get_llm_provider()
set_llm_provider(_provider)
if _provider == "ollama":
    _m = get_ollama_model()
    if _m:
        select_model(_m)

print("=" * 55)
print("  MoneyPrinterPro - YouTube Short Generator")
print("  Canal: Mind Glitch | Voz: Carlos (es-MX)")
print("  Imagenes: AI Horde (paralelo) + fallbacks")
print("=" * 55)

# ===== STEP 1: TOPIC =====
print("\n[1/7] Generando tema...")
topic = generate_text(
    "Genera una idea para un YouTube Short sobre un dato curioso de ciencia o misterio. "
    "Puede ser espacio, cerebro, fisica cuantica, biologia. "
    "Una oracion en espanol. Solo el tema, nada mas."
)
if len(topic) > 200:
    topic = topic[:200]
print(f"  >> {topic}")

# ===== STEP 2: SCRIPT =====
print("\n[2/7] Generando guion...")
script = generate_text(
    f"Genera un guion de 4 oraciones cortas para YouTube Short sobre: {topic}. "
    "Espanol latinoamericano. Directo al punto. Sin markdown. Solo texto plano."
)
script = re.sub(r"[*#\[\]{}]", "", script).strip()[:2000]
print(f"  >> {script[:300]}")

# ===== STEP 3: METADATA =====
print("\n[3/7] Generando metadata...")
title = generate_text(
    f"Titulo para YouTube Short sobre: {topic}. Espanol. 2 hashtags. Max 70 chars. Solo el titulo."
)
if len(title) > 100: title = title[:97] + "..."
description = generate_text(
    f"Descripcion corta YouTube sobre: {script[:200]}. Espanol. Max 150 chars. Solo la descripcion."
)
print(f"  Titulo: {title}")
print(f"  Desc: {description[:150]}")

# ===== STEP 4: IMAGE PROMPTS =====
print("\n[4/7] Generando prompts de imagen...")
prompts_raw = generate_text(
    f'Generate 4 short image prompts about: {topic}. '
    'Return ONLY a JSON array: ["prompt1","prompt2","prompt3","prompt4"]. '
    "English. Under 60 chars each. Vivid cinematic scenes. NO markdown."
)
prompts_raw = prompts_raw.replace("```json","").replace("```","").strip()
image_prompts = None
try:
    parsed = json.loads(prompts_raw)
    if isinstance(parsed, list):
        image_prompts = [str(p)[:80] for p in parsed if isinstance(p, str)]
except Exception:
    m = re.search(r"\[.*?\]", prompts_raw, re.DOTALL)
    if m:
        try: image_prompts = [str(p)[:80] for p in json.loads(m.group())]
        except: pass

if not image_prompts:
    image_prompts = [
        "Dramatic cosmic black hole emitting light in deep space",
        "Human brain neural connections glowing electric blue",
        "Quantum physics particles floating in dark void",
        "Ancient galaxy with swirling nebula and stars",
    ]
image_prompts = image_prompts[:4]
for i, p in enumerate(image_prompts):
    print(f"  {i+1}. {p}")

# ===== STEP 5: GENERATE IMAGES (PARALLEL AI HORDE) =====
print("\n[5/7] Generando imagenes via AI Horde (PARALELO - 4 a la vez)...")
print("  Submitting all 4 jobs at once to save time...")

HORDE_URL = "https://stablehorde.net/api/v2"
headers = {"apikey": "0000000000", "Content-Type": "application/json"}

# Submit ALL jobs at once
job_ids = []
for i, prompt in enumerate(image_prompts):
    payload = {
        "prompt": prompt[:200] + " ### cinematic, detailed, 4k",
        "params": {"width": 512, "height": 512, "steps": 15, "cfg_scale": 7, "sampler_name": "k_euler"},
        "nsfw": False, "models": ["stable_diffusion"], "r2": True,
    }
    try:
        resp = requests.post(f"{HORDE_URL}/generate/async", json=payload, headers=headers, timeout=30)
        if resp.status_code in (200, 202):
            jid = resp.json().get("id", "")
            job_ids.append(jid)
            print(f"  Job {i+1}: {jid[:12]}... submitted OK")
        else:
            job_ids.append("")
            print(f"  Job {i+1}: FAILED ({resp.status_code})")
    except Exception as e:
        job_ids.append("")
        print(f"  Job {i+1}: ERROR ({e})")

# Wait for ALL jobs (parallel = only wait once)
print("\n  Waiting for all images (they process in parallel)...")
results = [None] * len(job_ids)
pending = {i for i, jid in enumerate(job_ids) if jid}
t0 = time.time()

for tick in range(50):  # max ~4 min
    if not pending:
        break
    time.sleep(5)
    for i in list(pending):
        try:
            st = requests.get(f"{HORDE_URL}/generate/status/{job_ids[i]}", timeout=10).json()
            if st.get("done"):
                gens = st.get("generations", [])
                if gens and gens[0].get("img"):
                    img_resp = requests.get(gens[0]["img"], timeout=60)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        results[i] = img_resp.content
                        elapsed = time.time() - t0
                        print(f"  Image {i+1}: READY ({len(img_resp.content)//1024}KB, {elapsed:.0f}s)")
                pending.discard(i)
            elif st.get("faulted"):
                pending.discard(i)
                print(f"  Image {i+1}: FAULTED")
        except Exception:
            pass
    if pending and tick % 4 == 0:
        elapsed = time.time() - t0
        print(f"  [{elapsed:.0f}s] Still waiting for {len(pending)} images...")

# Save results + fallbacks
images = []
for i, (img_bytes, prompt) in enumerate(zip(results, image_prompts)):
    if img_bytes and len(img_bytes) > 1000:
        img_path = os.path.abspath(os.path.join(".mp", str(uuid4()) + ".png"))
        with open(img_path, "wb") as f: f.write(img_bytes)
        images.append(img_path)
    else:
        # Fallback: Picsum HD
        print(f"  Image {i+1}: Using Picsum fallback...")
        seed = abs(hash(prompt)) % 1000
        try:
            resp = requests.get(f"https://picsum.photos/seed/{seed}/1080/1920", timeout=30, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 5000:
                img_path = os.path.abspath(os.path.join(".mp", str(uuid4()) + ".png"))
                with open(img_path, "wb") as f: f.write(resp.content)
                images.append(img_path)
                print(f"  Image {i+1}: Picsum OK ({len(resp.content)//1024}KB)")
                continue
        except Exception:
            pass
        # Ultimate fallback: gradient
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1080, 1920), color=(25, 25, 80 + i*30))
        img_path = os.path.abspath(os.path.join(".mp", str(uuid4()) + ".png"))
        img.save(img_path)
        images.append(img_path)
        print(f"  Image {i+1}: Pillow fallback")

total_time = time.time() - t0
print(f"\n  All {len(images)} images ready in {total_time:.0f}s!")

# ===== STEP 6: TTS ESPAÑOL =====
print("\n[6/7] Generando voz en ESPANOL (Carlos, es-MX)...")
tts = TTS()
audio_path = os.path.abspath(os.path.join(".mp", str(uuid4()) + ".wav"))
clean_script = re.sub(r"[^\w\s.?!,]", "", script)
tts.synthesize(clean_script, audio_path)
print(f"  Audio: {os.path.getsize(audio_path)//1024}KB")

# ===== STEP 7: COMBINE VIDEO =====
print("\n[7/7] Combinando video final...")
from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, afx
from moviepy.video.fx.all import crop
from moviepy.config import change_settings

change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})

tts_clip = AudioFileClip(audio_path)
max_duration = tts_clip.duration
req_dur = max_duration / len(images)
print(f"  Duracion: {max_duration:.1f}s, {len(images)} imgs, {req_dur:.1f}s c/u")

clips = []
tot_dur = 0
while tot_dur < max_duration:
    for ip in images:
        if not os.path.exists(ip): continue
        clip = ImageClip(ip)
        clip.duration = req_dur
        clip = clip.set_fps(30)
        if round((clip.w/clip.h),4) < 0.5625:
            clip = crop(clip, width=clip.w, height=round(clip.w/0.5625), x_center=clip.w/2, y_center=clip.h/2)
        else:
            clip = crop(clip, width=round(0.5625*clip.h), height=clip.h, x_center=clip.w/2, y_center=clip.h/2)
        clip = clip.resize((1080, 1920))
        clips.append(clip)
        tot_dur += clip.duration

final_clip = concatenate_videoclips(clips).set_fps(30)

songs_dir = "Songs"
if os.path.isdir(songs_dir):
    songs = [f for f in os.listdir(songs_dir) if f.endswith((".mp3",".wav"))]
    if songs:
        song = AudioFileClip(os.path.join(songs_dir, random.choice(songs))).set_fps(44100)
        song = song.fx(afx.volumex, 0.1)
        final_clip = final_clip.set_audio(CompositeAudioClip([tts_clip.set_fps(44100), song]))
    else:
        final_clip = final_clip.set_audio(tts_clip)
else:
    final_clip = final_clip.set_audio(tts_clip)

final_clip = final_clip.set_duration(tts_clip.duration)
output_path = os.path.abspath("generated_short.mp4")
print(f"  Codificando video...")
final_clip.write_videofile(output_path, threads=2, logger="bar")

fs = os.path.getsize(output_path)
print(f"\n{'='*55}")
print(f"  VIDEO GENERADO EXITOSAMENTE!")
print(f"  Archivo: {output_path}")
print(f"  Tamano: {fs//1024}KB ({fs//(1024*1024)}MB)")
print(f"  Duracion: {max_duration:.1f}s | 1080x1920")
print(f"  Titulo: {title}")
print(f"{'='*55}")
