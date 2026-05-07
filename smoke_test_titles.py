"""Smoke test: generate_metadata() with 3 different scripts to inspect titles."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from classes.YouTube import YouTube

SCRIPTS = [
    {
        "subject": "La estrella que hizo explotar a su propia galaxia",
        "script": (
            "En el centro de la galaxia M87 hay un agujero negro supermasivo "
            "con seis mil quinientos millones de veces la masa del Sol. Cuando "
            "engulle materia, lanza un chorro de plasma a casi la velocidad de "
            "la luz que se extiende cinco mil años luz hacia afuera. Ese chorro "
            "calienta el gas intergaláctico y apaga la formación de nuevas "
            "estrellas en toda la galaxia. El propio agujero negro decide "
            "cuántas estrellas pueden nacer alrededor de él."
        ),
    },
    {
        "subject": "Por qué Venus gira al revés que el resto del sistema solar",
        "script": (
            "Venus es el único planeta del sistema solar que rota en sentido "
            "contrario a su órbita. Un día venusino dura doscientos cuarenta y "
            "tres días terrestres, más que su propio año. Los astrónomos creen "
            "que un impacto colosal en sus primeros mil millones de años "
            "volteó el planeta casi por completo. La atmósfera densa, cien "
            "veces más pesada que la terrestre, todavía arrastra esa rotación "
            "invertida con vientos de cuatrocientos kilómetros por hora."
        ),
    },
    {
        "subject": "La galaxia que va a chocar contra la Vía Láctea",
        "script": (
            "Andrómeda se acerca a nosotros a ciento diez kilómetros por "
            "segundo. En cuatro mil quinientos millones de años, las dos "
            "galaxias colisionarán y se fusionarán en una sola, apodada "
            "Lactómeda. A pesar del choque, casi ninguna estrella impactará "
            "con otra: las distancias entre ellas son tan enormes que "
            "atravesarán el sistema solar sin tocarlo. Lo que sí cambiará "
            "para siempre es el cielo nocturno de la Tierra."
        ),
    },
]


def make_instance(language: str) -> YouTube:
    # Bypass __init__ (it requires a Firefox profile). generate_metadata()
    # only needs: subject, script, language, generate_response().
    yt = YouTube.__new__(YouTube)
    yt._language = language
    yt._niche = "universo, ciencia, galaxias"
    return yt


def main() -> None:
    yt = make_instance("Spanish")
    for i, item in enumerate(SCRIPTS, 1):
        yt.subject = item["subject"]
        yt.script = item["script"]
        print(f"\n{'='*70}\n[{i}] SUBJECT: {item['subject']}\n{'='*70}")
        meta = yt.generate_metadata()
        print(f"TITLE      : {meta['title']}")
        print(f"DESCRIPTION:\n{meta['description']}")


if __name__ == "__main__":
    main()
