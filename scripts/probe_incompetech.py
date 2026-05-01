import requests
import urllib3

urllib3.disable_warnings()

r = requests.get(
    "https://incompetech.com/music/royalty-free/pieces.json",
    timeout=30,
    verify=False,
    headers={"User-Agent": "Mozilla/5.0"},
)
catalog = r.json()

KEYWORDS = [
    "cosmos",
    "vastness",
    "light years",
    "adhafera",
    "scifi",
    "sci-fi",
    "transcending",
    "mercury",
    "feedback",
    "cold moon",
    "blazing",
    "darkness below",
    "automatons",
]

for kw in KEYWORDS:
    hits = [
        (rec.get("title", "").strip(), rec.get("filename", "").strip())
        for rec in catalog
        if kw in rec.get("title", "").lower() or kw in rec.get("filename", "").lower()
    ]
    print(f"\n=== {kw!r} ({len(hits)} hits) ===")
    for t, f in hits[:8]:
        print(f"  title={t!r}  file={f!r}")
