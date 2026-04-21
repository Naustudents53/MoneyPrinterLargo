"""
One-shot cleanup: remove duplicate entries from .mp/youtube.json using the
exact same detection algorithm as YouTube.generate_topic() so that what the
cleanup deletes is what the guard would now prevent.

Strategy: for each account, walk the videos list in order. Keep video N if
_is_duplicate(N.subject|N.title, kept_so_far) == False. Otherwise drop it.
This preserves the first occurrence of each topic.
"""

import json
import os
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".mp", "youtube.json")

ES_STOP = {
    "el","la","los","las","de","del","que","y","en","un","una","por","para",
    "con","se","su","sus","lo","al","como","es","fue","era","ser","son","mas",
    "este","esta","esto","estos","estas","sobre","entre","pero","si","no","ni",
    "cuando","donde","quien","cual","cuales","hacia","desde","hasta","sin","ya",
    "muy","menos","todo","toda","todos","todas","otro","otra","otros","otras",
    "tambien","solo","tras","ante","bajo",
}
EN_STOP = {
    "the","of","a","an","and","is","was","to","in","on","who","why","how",
    "what","were","are","be","been","have","has","had","with","from","that",
    "this","these","those","will","would","can","could","should","about","into",
    "which","where","when","their","its","it","by","at","as","or","but","for",
}
STOP = ES_STOP | EN_STOP
SENTENCE_STARTERS = {
    "el","la","los","las","un","una","the","a","an","cuando","como","donde",
    "por","que","cual","hay","esta","este","ese","esa","aquel",
}
COMMON_CAP_NOISE = {
    "antigua","antiguo","antiguos","antiguas","historia","historico","historica",
    "mundo","dios","dioses","rey","reina","emperador","faraon","sabio",
    "filosofo","filosofos","filosofia","legado","misterio","misterios","secreto",
    "secretos","enigma","leyenda","epoca","siglo","era","anyo","ano","anos",
    "imperio","reino","templo","ciudad","ciudades","conquista","batalla","guerra",
    "muerte","vida","revolucion","civilizacion","civilizaciones","new","ancient",
    "great","lost","hidden","secret","mysterious","age","bronze","iron","stone",
    "city","cities","temple","empire","kingdom","dynasty","war","battle",
    "roma","grecia","egipto","china","persia","mesopotamia","babilonia","india",
    "japon","europa","asia","africa","america","italia","espanya","francia",
    "inglaterra","alemania","turquia","atenas","esparta","alejandria",
    "constantinopla","oriente","occidente","mediterraneo","nilo","tigris",
    "eufrates","renacimiento","medieval","barroco","ilustracion",
}


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def strip_markdown(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`+", "", s)
    # Strip hashtags: #Foo, #HistoriaAntigua, #Neuro. Every video on the same
    # channel reuses a small pool of tags, so they'd always collide as
    # "shared entities" and produce false positives.
    s = re.sub(r"#\w+", " ", s, flags=re.UNICODE)
    s = re.sub(r"[*_#]+", "", s)
    s = re.sub(r"^\s*(?:topic|tema|title|t[ií]tulo)\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" \t\"'“”‘’«»").strip()
    return s


def normalize(s: str) -> str:
    s = strip_diacritics(s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(t for t in s.split() if t and t not in STOP and len(t) > 1)


def extract_entities(original: str) -> set:
    text = strip_markdown(original)
    ents: set = set()
    raw = re.findall(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü0-9']+", text)
    for i, tok in enumerate(raw):
        norm = strip_diacritics(tok.lower())
        # Skip pure numbers (including years) — a shared year between unrelated
        # events is not a distinctive signature.
        if re.fullmatch(r"\d+", tok):
            continue
        if re.fullmatch(r"[IVXLCDM]{2,}", tok):
            ents.add(norm)
            continue
        if (
            tok[0].isupper()
            and i > 0
            and norm not in STOP
            and norm not in SENTENCE_STARTERS
            and norm not in COMMON_CAP_NOISE
            and len(tok) >= 3
            and not tok.isupper()
        ):
            ents.add(norm)
    return ents


def is_duplicate(candidate_texts: list, past_list: list) -> tuple:
    """
    candidate_texts: list of strings describing the current video (subject + title).
    past_list: list of dicts {texts: [subject, title], entities: set, norm: str}
    Returns (dup: bool, reason: str, matched_past_index: int or None)
    """
    if not past_list:
        return False, "", None

    # Frequency of each entity across past texts
    freq: Counter = Counter()
    for p in past_list:
        freq.update(p["entities"])
    common_threshold = max(3, len(past_list) // 7)
    common = {e for e, c in freq.items() if c > common_threshold}

    # Compute candidate signatures (merge of all texts — subject + title)
    cand_norm_all = " ".join(normalize(t) for t in candidate_texts if t)
    cand_ents = set()
    for t in candidate_texts:
        cand_ents |= extract_entities(strip_markdown(t or ""))

    for idx, p in enumerate(past_list):
        p_norm = p["norm"]
        p_ents = p["entities"]
        if not p_norm:
            continue
        if cand_norm_all == p_norm:
            return True, "exact", idx
        shared = (cand_ents & p_ents) - common
        if shared:
            return True, f"entity:{sorted(shared)}", idx
        a, b = set(cand_norm_all.split()), set(p_norm.split())
        if a and b:
            overlap = len(a & b) / max(len(a), len(b))
            if overlap >= 0.55:
                return True, f"overlap:{overlap:.2f}", idx
        if SequenceMatcher(None, cand_norm_all, p_norm).ratio() >= 0.7:
            return True, "seq-sim", idx
    return False, "", None


def main():
    with open(CACHE, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_before = 0
    total_removed = 0
    removed_log = []

    for acc in data.get("accounts", []):
        videos = acc.get("videos", [])
        total_before += len(videos)
        kept = []
        kept_sigs = []
        for v in videos:
            subject = v.get("subject", "") or ""
            title = v.get("title", "") or ""
            texts = [t for t in (subject, title) if t]
            dup, reason, matched_idx = is_duplicate(texts, kept_sigs)
            if dup:
                total_removed += 1
                matched_first_text = (
                    kept_sigs[matched_idx]["texts"][0] if matched_idx is not None else ""
                )
                removed_log.append(
                    {
                        "account": acc.get("nickname", acc.get("id", "?")),
                        "date": v.get("date", ""),
                        "subject": subject[:120],
                        "title": title[:120],
                        "reason": reason,
                        "matched_date": (
                            kept[matched_idx].get("date", "")
                            if matched_idx is not None and matched_idx < len(kept)
                            else ""
                        ),
                        "matched_subject": strip_markdown(matched_first_text)[:120],
                    }
                )
                continue
            kept.append(v)
            merged_norm = " ".join(normalize(t) for t in texts if t)
            merged_ents: set = set()
            for t in texts:
                merged_ents |= extract_entities(strip_markdown(t))
            kept_sigs.append({"texts": texts, "norm": merged_norm, "entities": merged_ents})
        acc["videos"] = kept

    print(f"Videos before : {total_before}")
    print(f"Duplicates removed: {total_removed}")
    print(f"Videos after  : {total_before - total_removed}")
    print()
    for r in removed_log:
        print(f"[{r['account']}] removed  {r['date']}  reason={r['reason']}")
        print(f"   subject: {strip_markdown(r['subject'])}")
        print(f"   kept   : {r['matched_date']}  — {r['matched_subject']}")
        print()

    # Write back only if --apply is passed; otherwise dry-run.
    if "--apply" in sys.argv:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"APPLIED — wrote {CACHE}")
    else:
        print("DRY RUN — pass --apply to write changes.")


if __name__ == "__main__":
    main()
