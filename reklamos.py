import base64
import datetime
import urllib.request

# =====================================================================
# ČIA ĮRAŠYKITE SAVO AKTYVIAS REKLAMAS (SĄRAŠAS)
# =====================================================================
# "leidinys": "religija", "kultura" arba "abi"
# "nuo" / "iki": data YYYY-MM-DD formatu (jei tuščia "", galioja visada)
REKLAMOS_SARASAS = [
    # 1 REKLAMA: Rodyti abiejuose leidiniuose, be pabaigos datos (galioja visada)
    {
        "leidinys": "abi",
        "nuo": "2026-08-01",
        "iki": "",
        "img": "https://raw.githubusercontent.com/Bernardinai/bernardinai/main/reklama_test.jpg",
        "link": "https://www.bernardinai.lt/parama",
        "title": "Parama Bernardinams",
    },
    # Galite pridėti kiek norite reklamų, atskirdami kableliais:
    # {
    #     "leidinys": "kultura",
    #     "nuo": "2026-08-01",
    #     "iki": "2026-09-01",
    #     "img": "https://...",
    #     "link": "https://...",
    #     "title": "Knygos reklama"
    # },
]
# =====================================================================


def _gauti_b64_img(url):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    " AppleWebKit/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            c_type = resp.headers.get_content_type() or "image/jpeg"
            b64_str = base64.b64encode(resp.read()).decode("utf-8")
            return f"data:{c_type};base64,{b64_str}"
    except Exception as e:
        print(f"Nepavyko konvertuoti reklamos į base64: {e}")
        return url


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

        if tinka_leidinys and tinka_data and r.get("img"):
            tinkamos.append(r)

    # 2. Jei turime reklamų – sukame karuselę
    if tinkamos:
        r = tinkamos[vieta_idx % len(tinkamos)]
        img_src = r["img"]
        if formatas == "pdf":
            img_src = _gauti_b64_img(img_src)

        link_url = r.get("link", "#")
        title = r.get("title", "Reklama")

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

    # 3. Jei reklamų nėra – rodomas standartinis kvietimas
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
