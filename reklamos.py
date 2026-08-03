import base64
import datetime
import os

# =====================================================================
# ČIA ĮRAŠYKITE SAVO AKTYVIAS REKLAMAS
# =====================================================================
# "leidinys": "religija", "kultura" arba "abi"
# "nuo" / "iki": data YYYY-MM-DD formatu (jei tuščia "", galioja visada)
# "failas": paveikslėlio failo pavadinimas esantis folderyje /reklamos/
REKLAMOS_SARASAS = [
    # 1 REKLAMA: MoreMins
    {
        "leidinys": "abi",
        "nuo": "2026-08-01",
        "iki": "",
        "failas": "moremins-esim.png",
        "link": "https://www.moremins.com/lt/app/login?ref=y2njoty&setCoupon=BERNARDINAI&partner=bernardinai",
        "title": "Keliaudami naudokitės pigesniais mobiliasiais duomenimis su MoreMins ir Bernardinai.lt!",
    },
    # Pavyzdys kitai reklamai:
    # {
    #     "leidinys": "kultura",
    #     "nuo": "2026-08-01",
    #     "iki": "2026-09-01",
    #     "failas": "nauja_knyga.png",
    #     "link": "https://www.leidykla.lt/knyga",
    #     "title": "Knygos reklama"
    # },
]
# =====================================================================

# GitHub repozitorijos informacija MailerLite laiškams:
GITHUB_OWNER = "Bernardinai"
GITHUB_REPO = "bernardinai"
GITHUB_BRANCH = "main"


def _gauti_vietinio_failo_src(failo_pavadinimas, formatas="pdf"):
    failo_kelias = os.path.join("reklamos", failo_pavadinimas)

    # 1. JEI GENERUOJAME PDF – skaitome failą tiesiai iš disko ir verčiame į base64
    if formatas == "pdf":
        if os.path.exists(failo_kelias):
            try:
                with open(failo_kelias, "rb") as f:
                    ext = failo_pavadinimas.lower()
                    c_type = (
                        "image/png"
                        if ext.endswith(".png")
                        else (
                            "image/webp"
                            if ext.endswith(".webp")
                            else "image/jpeg"
                        )
                    )
                    b64_str = base64.b64encode(f.read()).decode("utf-8")
                    return f"data:{c_type};base64,{b64_str}"
            except Exception as e:
                print(f"Nepavyko perskaityti vietinio failo '{failo_kelias}': {e}")
        else:
            print(
                f"DĖMESIO: Failas '{failo_kelias}' nerastas reklamos folderyje!"
            )
        return ""

    # 2. JEI GENERUOJAME EL. LAIŠKĄ – grąžiname viešą GitHub raw nuorodą
    else:
        return (
            f"https://raw.githubusercontent.com/{GITHUB_OWNER}/"
            f"{GITHUB_REPO}/{GITHUB_BRANCH}/reklamos/{failo_pavadinimas}"
        )


def gauti_reklamos_bloka(leidinio_tipas, vieta_idx=0, formatas="pdf"):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # 1. Atrinkime galiojančias reklamas
    tinkamos = []
    for r in REKLAMOS_SARASAS:
        tinka_leidinys = r.get("leidinys", "").lower() in [
            leidinio_tipas.lower(),
            "abi",
        ]
        nuo = r.get("nuo", "")
        iki = r.get("iki", "")
        tinka_data = (not nuo or nuo <= today_str) and (
            not iki or today_str <= iki
        )

        if tinka_leidinys and tinka_data and r.get("failas"):
            tinkamos.append(r)

    # 2. Jei turime galiojančių reklamų – sukame karuselę
    if tinkamos:
        r = tinkamos[vieta_idx % len(tinkamos)]
        img_src = _gauti_vietinio_failo_src(r["failas"], formatas)
        link_url = r.get("link", "#")
        title = r.get("title", "Reklama")

        if img_src:
            if formatas == "pdf":
                return f"""
        <div class="ad-box" style="padding: 0; border: none; background: transparent; margin: 30px auto;">
            <a href="{link_url}">
                <img src="{img_src}" alt="{title}" style="width: 100%; max-width: 420px; height: auto; border-radius: 6px; display: block; margin: 0 auto;">
            </a>
        </div>
                """
            else:
                return f"""
        <div style="text-align: center; margin: 30px 0; padding: 15px 0; border-top: 1px solid #eee; border-bottom: 1px solid #eee;">
            <a href="{link_url}" target="_blank" rel="noopener noreferrer">
                <img src="{img_src}" alt="{title}" style="width: 100%; max-width: 600px; height: auto; border-radius: 6px; display: inline-block;">
            </a>
        </div>
                """

    # 3. Jei reklamų nėra arba nerastas failas – rodomas standartinis kvietimas
    if formatas == "pdf":
        return """
        <div class="ad-box">
            <div class="ad-title">Čia galėtų būti Jūsų reklama</div>
            <div class="ad-contact">Kreipkitės: <a href="mailto:reklama@bernardinai.lt">reklama@bernardinai.lt</a></div>
        </div>
        """
    else:
        return """
        <div style="margin: 30px auto; padding: 15px; background-color: #fcfcfc; border: 1px dashed #ccc; border-radius: 6px; text-align: center; max-width: 500px;">
            <div style="font-size: 13px; font-weight: bold; color: #444; text-transform: uppercase; margin-bottom: 5px;">Čia galėtų būti Jūsų reklama</div>
            <div style="font-size: 13px; color: #666;">Kreipkitės: <a href="mailto:reklama@bernardinai.lt" style="color: #7a2222; font-weight: bold; text-decoration: none;">reklama@bernardinai.lt</a></div>
        </div>
        """
