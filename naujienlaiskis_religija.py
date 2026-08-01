import base64
import datetime
from datetime import timedelta
import feedparser
import json
import os
import re
import sys
import traceback
import urllib.error
import urllib.request
from weasyprint import HTML
from zoneinfo import ZoneInfo

event_name = os.environ.get("EVENT_NAME", "")
force_real = os.environ.get("TIKRAS_LEIDINYS", "false").lower() == "true"
is_real_run = (event_name == "schedule") or force_real

if event_name == "schedule":
    lt_time = datetime.datetime.now(ZoneInfo("Europe/Vilnius"))
    if not (6 <= lt_time.hour <= 10):
        print(
            f"Dabar Lietuvoje yra {lt_time.hour} val. Agentas ilsisi, nes"
            " siuntimo laikas yra tarp 06:00 ir 10:00 val."
        )
        sys.exit(0)

today = datetime.datetime.now()
today_str = today.strftime("%Y-%m-%d")
one_week_ago = today - timedelta(days=7)
menesiai = [
    "sausio",
    "vasario",
    "kovo",
    "balandžio",
    "gegužės",
    "birželio",
    "liepos",
    "rugpjūčio",
    "rugsėjo",
    "spalio",
    "lapkričio",
    "gruodžio",
]

leidinio_data = f"{today.year} m. {menesiai[today.month - 1]} {today.day} d."
savaites_laikotarpis = (
    f"{one_week_ago.year} m. {menesiai[one_week_ago.month - 1]}"
    f" {one_week_ago.day} d. – {today.year} m. {menesiai[today.month - 1]}"
    f" {today.day} d."
)

tracker_file = "leidinio_numeris_religija.txt"
current_year = today.year
numeris = 1

if is_real_run:
    if os.path.exists(tracker_file):
        try:
            with open(tracker_file, "r", encoding="utf-8") as f:
                data = f.read().strip().split("/")
                saved_year = int(data[0])
                saved_num = int(data[1])
                last_run_date = data[2] if len(data) == 3 else ""

                if saved_year == current_year:
                    if last_run_date == today_str:
                        numeris = saved_num
                    else:
                        numeris = saved_num + 1
                else:
                    numeris = 1
        except Exception:
            pass
    leidinio_numeris = f"{current_year}/{numeris}"
else:
    leidinio_numeris = "Bandomasis"

# --- Funkcijos ankstesnio numerio gavėjų skaičiui ir linksniui gauti ---
api_key = os.environ.get("MAILERLITE_API_KEY")


def gauti_linksni(skaicius):
    paskutiniai_du = skaicius % 100
    paskutinis = skaicius % 10
    if 11 <= paskutiniai_du <= 19 or paskutinis == 0:
        return "prenumeratorių"
    elif paskutinis == 1:
        return "prenumeratoriui"
    else:
        return "prenumeratoriams"


def gauti_paskutines_kampanijos_gavejus(api_key):
    if not api_key:
        return None
    try:
        url = "https://api.mailerlite.com/api/v2/campaigns/sent"
        req = urllib.request.Request(
            url,
            headers={
                "X-MailerLite-ApiKey": api_key,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urllib.request.urlopen(req) as response:
            kampanijos = json.loads(response.read().decode("utf-8"))
            if kampanijos and len(kampanijos) > 0:
                paskutine = kampanijos[0]
                return paskutine.get(
                    "total_recipients", paskutine.get("recipients_count", 0)
                )
    except Exception as e:
        print(f"Nepavyko gauti praėjusio numerio gavėjų skaičiaus: {e}")
    return None


# Suformuojame ankstesnio numerio eilutę
ankstesnio_nr_tekstas = ""
if is_real_run and numeris > 1:
    ankstesnis_nr_str = f"{current_year}/{numeris - 1}"
    gaveju_sk = gauti_paskutines_kampanijos_gavejus(api_key)
    if gaveju_sk and gaveju_sk > 0:
        linksnis = gauti_linksni(gaveju_sk)
        ankstesnio_nr_tekstas = (
            f"Ankstesnis savaitraščio numeris (Nr. {ankstesnis_nr_str}) buvo"
            f" išsiųstas {gaveju_sk} {linksnis}."
        )
    else:
        ankstesnio_nr_tekstas = (
            f"Ankstesnis savaitraščio numeris (Nr. {ankstesnis_nr_str}) jau"
            " pasiekė mūsų skaitytojus."
        )
elif not is_real_run:
    gaveju_sk = gauti_paskutines_kampanijos_gavejus(api_key)
    if gaveju_sk and gaveju_sk > 0:
        linksnis = gauti_linksni(gaveju_sk)
        ankstesnio_nr_tekstas = (
            "Ankstesnis savaitraščio numeris buvo išsiųstas"
            f" {gaveju_sk} {linksnis}."
        )
# -----------------------------------------------------------------------------

logo_src = ""
logo_failas = "logo.png"
if os.path.exists(logo_failas):
    with open(logo_failas, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        logo_src = f"data:image/png;base64,{encoded_string}"

matyti_url = set()
pagrindiniai_straipsniai = []
kiti_straipsniai = []


def apdoroti_straipsni(entry, is_main=True):
    link = getattr(entry, "link", "#")
    if link in matyti_url:
        return None

    # --- Neįtraukiame paties „Religijos savaitraščio“ straipsnių ---
    title_lower = getattr(entry, "title", "").lower()
    if (
        "religijos naujienų" in title_lower
        or "tikėjimo savaitraštis" in title_lower
        or "savaitraštis nr." in title_lower
    ):
        print(
            f"Praleidžiamas savaitraščio įrašas: {getattr(entry, 'title', '')}"
        )
        return None
    # ----------------------------------------------------------------

    try:
        pub_date_obj = datetime.datetime(*entry.published_parsed[:6])
        if pub_date_obj < one_week_ago:
            return None
        data_lt = (
            f"{pub_date_obj.year} m. {menesiai[pub_date_obj.month - 1]}"
            f" {pub_date_obj.day} d."
        )
    except:
        pub_date_obj = datetime.datetime.now()
        data_lt = "Data nežinoma"

    saltinis = "Bernardinai.lt"
    if not is_main:
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            saltinis = entry.source.title

    autorius = getattr(entry, "author", "Bernardinai.lt")
    aprasymas = getattr(entry, "description", "")

    izanga_clean = re.sub("<[^<]+>", "", aprasymas)
    izanga_clean = (
        izanga_clean[:250] + "..."
        if len(izanga_clean) > 250
        else izanga_clean
    )

    # --- 4 pakopų nuotraukos paieška (užtikrina, kad neliktų be foto) ---
    tituline_nuotrauka = ""

    # 1. Tikriname RSS <media:content>
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if "url" in media:
                tituline_nuotrauka = media["url"]
                break

    # 2. Tikriname RSS <enclosure>
    if not tituline_nuotrauka and hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/") or enc.get("href", "").endswith((".jpg", ".jpeg", ".png", ".webp")):
                tituline_nuotrauka = enc.get("href", "")
                break

    # 3. Tikriname <img src="..."> aprašyme
    if not tituline_nuotrauka:
        paveikslelis = re.search(r'<img[^>]+src="([^">]+)"', aprasymas)
        if paveikslelis:
            tituline_nuotrauka = paveikslelis.group(1)

    # 4. Jei nėra, ieškome pirmos nuotraukos pačiame straipsnio tekste
    if not tituline_nuotrauka and hasattr(entry, "content") and len(entry.content) > 0:
        paveikslelis_tekste = re.search(r'<img[^>]+src="([^">]+)"', entry.content[0].value)
        if paveikslelis_tekste:
            tituline_nuotrauka = paveikslelis_tekste.group(1)
    # --------------------------------------------------------------------

    pilnas_tekstas = (
        entry.content[0].value
        if (hasattr(entry, "content") and len(entry.content) > 0)
        else aprasymas
    )

    if is_main:
        pilnas_tekstas = re.sub(r"<img[^>]*>", "", pilnas_tekstas)
        pilnas_tekstas = re.sub(
            r"<figcaption[^>]*>.*?</figcaption>",
            "",
            pilnas_tekstas,
            flags=re.IGNORECASE | re.DOTALL,
        )
        pilnas_tekstas = re.sub(
            r'<p[^>]*class="[^"]*caption[^"]*"[^>]*>.*?</p>',
            "",
            pilnas_tekstas,
            flags=re.IGNORECASE | re.DOTALL,
        )
        pilnas_tekstas = re.sub(
            r'<div[^>]*class="[^"]*caption[^"]*"[^>]*>.*?</div>',
            "",
            pilnas_tekstas,
            flags=re.IGNORECASE | re.DOTALL,
        )
    else:
        saltinis_match = re.search(
            r"(?:<p>)?\s*(?:<strong>)?\s*Šaltinis\s*(?:</strong>)?\s*:\s*([^<]+)",
            pilnas_tekstas,
            re.IGNORECASE,
        )
        if saltinis_match:
            saltinis = saltinis_match.group(1).strip()
            pilnas_tekstas = pilnas_tekstas.replace(
                saltinis_match.group(0), ""
            )

    pilnas_tekstas = re.sub(
        r"<h([1-6])\b[^>]*>",
        r'<div class="heading-\1">',
        pilnas_tekstas,
        flags=re.IGNORECASE,
    )
    pilnas_tekstas = re.sub(
        r"</h[1-6]>", r"</div>", pilnas_tekstas, flags=re.IGNORECASE
    )
    pilnas_tekstas = re.sub(
        r"(<p[^>]*>)\s*([A-ZĄČĘĖĮŠŲŪŽa-ząčęėįšųūž])",
        r'\1<span class="drop-cap">\2</span>',
        pilnas_tekstas,
        count=1,
    )

    matyti_url.add(link)
    return {
        "title": entry.title.replace("\n", " ").replace("\r", "").strip(),
        "author": autorius,
        "source": saltinis,
        "date": data_lt,
        "pub_date_obj": pub_date_obj,
        "image": tituline_nuotrauka,
        "excerpt": izanga_clean,
        "content": pilnas_tekstas,
        "link": link,
    }


print("Nuskaitomas pagrindinis RSS srautas (Religija)...")
for puslapis in range(1, 10):
    rss_url = (
        f"https://www.bernardinai.lt/feed/mailerlite-religija/?paged={puslapis}"
    )
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        break
    for entry in feed.entries:
        straipsnis = apdoroti_straipsni(entry, is_main=True)
        if straipsnis:
            pagrindiniai_straipsniai.append(straipsnis)

print("Nuskaitomas papildomas Religijos RSS srautas...")
for puslapis in range(1, 10):
    rss_url = (
        "https://www.bernardinai.lt/feed/mailerlite-religija-visi/?paged="
        f"{puslapis}"
    )
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        break
    for entry in feed.entries:
        straipsnis = apdoroti_straipsni(entry, is_main=False)
        if straipsnis:
            kiti_straipsniai.append(straipsnis)

pagrindiniai_straipsniai.sort(key=lambda x: x["pub_date_obj"])
kiti_straipsniai.sort(key=lambda x: x["pub_date_obj"])

print(
    f"Iš viso atrinkta: {len(pagrindiniai_straipsniai)} pagrindinių ir"
    f" {len(kiti_straipsniai)} papildomų straipsnių."
)

cover_bg_image = ""
for straipsnis in reversed(pagrindiniai_straipsniai):
    if straipsnis.get("image"):
        cover_bg_image = straipsnis["image"]
        break

if not cover_bg_image:
    for straipsnis in reversed(kiti_straipsniai):
        if straipsnis.get("image"):
            cover_bg_image = straipsnis["image"]
            break

html_kodas = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 20mm 15mm 20mm 15mm;
        @bottom-center {{
            content: counter(page); font-family: 'Georgia', serif; font-size: 11pt; color: #7a2222;
        }}
    }}
    @page cover {{ margin: 0; @bottom-center {{ content: none; }} }}
    html, body {{ margin: 0; padding: 0; }}
    body {{ font-family: 'Georgia', serif; color: #222; line-height: 1.6; font-size: 11pt; }}
    
    .cover-page {{ page: cover; position: relative; width: 210mm; height: 297mm; background-color: #1a1a1a; overflow: hidden; }}
    .bg-img {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }}
    .overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(26, 26, 26, 0.70); z-index: 2; }}
    .cover-content {{ position: absolute; top: 48%; left: 50%; transform: translate(-50%, -50%); text-align: center; width: 88%; color: white; z-index: 3; }}
    .logo-container {{ background-color: rgba(255, 255, 255, 0.9); padding: 15px 30px; border-radius: 12px; display: inline-block; margin-bottom: 25px; box-shadow: 0 5px 15px rgba(0,0,0,0.3); }}
    .logo-main {{ max-width: 220px; display: block; }}
    .main-title {{ font-size: 34pt; font-weight: bold; margin-bottom: 15px; letter-spacing: 1px; text-transform: uppercase; line-height: 1.15; }}
    .sub-title {{ font-size: 16pt; color: #E0E0E0; margin-bottom: 30px; font-style: italic; }}
    .divider {{ width: 80px; height: 3px; background-color: #d32f2f; margin: 0 auto 30px auto; }}
    .meta-box {{ display: inline-block; background-color: rgba(0,0,0,0.5); padding: 15px 30px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); }}
    .meta {{ font-size: 9.5pt; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.8; white-space: nowrap; }}
    
    .toc-page {{ page-break-before: always; page-break-after: always; padding-top: 10mm; }}
    .toc-title {{ text-align: center; font-size: 24pt; color: #7a2222; text-transform: uppercase; margin-bottom: 30px; margin-top: 20px; }}
    .toc-list {{ list-style: none; padding: 0; margin: 0; }}
    .toc-item {{ border-bottom: 1px dotted #ccc; margin-bottom: 15px; padding-bottom: 5px; overflow: hidden; }}
    .toc-link {{ text-decoration: none; color: #222; display: block; }}
    .toc-section-title {{ font-size: 14pt; color: #7a2222; font-weight: bold; text-transform: uppercase; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #7a2222; padding-bottom: 5px; }}
    .intro-box {{ background-color: #f9f9f9; padding: 30px; border-radius: 8px; border: 1px solid #eaeaea; margin: 35px auto 30px auto; max-width: 500px; text-align: center; }}
    .btn-support {{ display: inline-block; background-color: #d32f2f; color: #FFF; padding: 10px 20px; text-decoration: none; font-weight: bold; border-radius: 4px; margin-top: 15px; }}
    
    .article-columns {{ column-count: 2; column-gap: 30px; text-align: justify; }}
    .drop-cap {{ font-size: 350%; float: left; margin: 4px 8px 0 0; color: #7a2222; line-height: 0.8; font-weight: bold; }}
    .article-columns p {{ margin-top: 0; margin-bottom: 15px; widows: 2; orphans: 2; }}
    
    .article-page {{
        margin-top: 40px;
        padding-top: 30px;
        border-top: 1px solid #cccccc;
    }}
    .article-page:first-of-type {{
        margin-top: 0;
        padding-top: 0;
        border-top: none;
    }}
    .article-top-block {{
        break-inside: avoid;
        page-break-inside: avoid;
        break-after: avoid;
        page-break-after: avoid;
        margin-bottom: 25px;
    }}
    .article-header {{ text-align: center; margin-bottom: 20px; }}
    .article-title {{ font-size: 26pt; font-weight: bold; margin-bottom: 10px; line-height: 1.2; }}
    .article-meta {{ font-size: 10pt; color: #666; text-transform: uppercase; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
    .article-image {{ width: 100%; max-height: 400px; object-fit: cover; margin-top: 15px; border-radius: 4px; }}
    
    .other-articles-section {{ page-break-before: always; padding-top: 10mm; }}
    .other-section-header {{ text-align: center; font-size: 24pt; font-weight: bold; color: #7a2222; text-transform: uppercase; margin-bottom: 10px; border-bottom: 2px solid #7a2222; padding-bottom: 10px; }}
    .other-section-subtitle {{ text-align: center; font-size: 10pt; color: #666; margin-bottom: 30px; font-style: italic; padding: 0 10%; line-height: 1.5; }}
    .other-article {{ margin-bottom: 40px; }}
    .other-article-top-block {{
        break-inside: avoid;
        page-break-inside: avoid;
        break-after: avoid;
        page-break-after: avoid;
        margin-bottom: 15px;
    }}
    .other-article-title {{ font-size: 16pt; font-weight: bold; margin-bottom: 8px; line-height: 1.2; color: #111; }}
    .other-article-meta {{ font-size: 9pt; color: #666; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
    .other-article img {{ width: 100% !important; height: auto !important; max-height: 300px; object-fit: cover; border-radius: 4px; margin-bottom: 5px; }}
    .other-article figure, .other-article .wp-caption {{ margin: 0 0 15px 0; width: 100% !important; break-inside: avoid; page-inside: avoid; }}
    .other-article figcaption, .other-article .wp-caption-text {{ font-size: 8pt; color: #777; font-style: italic; text-align: center; line-height: 1.3; margin-top: 5px; }}
    
    .ad-box {{
        margin: 35px auto 20px auto;
        padding: 16px 24px;
        background-color: #fcfcfc;
        border: 1px dashed #cccccc;
        border-radius: 6px;
        text-align: center;
        max-width: 420px;
        break-inside: avoid;
        page-break-inside: avoid;
    }}
    .ad-title {{
        font-size: 10pt;
        font-weight: bold;
        color: #444444;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 5px;
    }}
    .ad-contact {{
        font-size: 9.5pt;
        color: #666666;
    }}
    .ad-contact a {{
        color: #7a2222;
        text-decoration: none;
        font-weight: bold;
    }}
    
    .back-to-toc {{ text-align: right; margin-top: 15px; font-size: 9pt; }}
    .back-to-toc a {{ color: #7a2222; text-decoration: none; }}
    
    .contacts-page {{ page-break-before: always; padding-top: 10mm; }}
</style>
</head>
<body>
    <div class="cover-page">
        {f'<img src="{cover_bg_image}" class="bg-img">' if cover_bg_image else ''}
        <div class="overlay"></div>
        <div class="cover-content">
            <div class="logo-container">
                {f'<img src="{logo_src}" class="logo-main">' if logo_src else '<div style="color:#111; font-size: 24pt; font-weight:bold;">Bernardinai.lt</div>'}
            </div>
            <div class="main-title">Religijos naujienų ir<br>tikėjimo savaitraštis</div>
            <div class="sub-title">Geriausi savaitės tekstai vienoje vietoje</div>
            <div class="divider"></div>
            <div class="meta-box">
                <div class="meta">
                    <strong>Leidinio data:</strong> {leidinio_data}<br>
                    <strong>Numeris:</strong> {leidinio_numeris}<br>
                    <strong>Laikotarpis:</strong> {savaites_laikotarpis}
                </div>
            </div>
        </div>
    </div>

    <div class="toc-page" id="turinys">
        <div class="toc-title">Turinys</div>
        <div class="toc-section-title">Savaitės svarbiausi</div>
        <ul class="toc-list">
"""

for i, straipsnis in enumerate(pagrindiniai_straipsniai):
    html_kodas += f"""<li class="toc-item"><a href="#pagrindinis_{i}" class="toc-link"><strong>{straipsnis['title']}</strong></a></li>"""

if kiti_straipsniai:
    html_kodas += """
        </ul>
        <div class="toc-section-title">Kiti savaitės religijos ir tikėjimo tekstai</div>
        <ul class="toc-list">
"""
    for i, straipsnis in enumerate(kiti_straipsniai):
        html_kodas += f"""<li class="toc-item"><a href="#kitas_{i}" class="toc-link"><strong>{straipsnis['title']}</strong></a></li>"""

html_kodas += f"""
        </ul>
        {f'<div style="background-color: #fcfcfc; border-left: 4px solid #7a2222; padding: 12px 18px; margin: 35px auto 10px auto; max-width: 464px; font-size: 10pt; color: #444; font-style: italic; text-align: center;">{ankstesnio_nr_tekstas}</div>' if ankstesnio_nr_tekstas else ''}
        <div class="intro-box">
            <h3 style="margin-top: 0; color: #222; font-size: 16pt;">Palaikykite mūsų veiklą</h3>
            <p style="color: #555;">Bernardinai.lt yra nepriklausomas leidinys, savo misiją tęsiantis išskirtinai skaitytojų paramos dėka. Kviečiame mus paremti.</p>
            <a href="https://www.bernardinai.lt/parama" class="btn-support">Paremkite mus</a>
        </div>
    </div>
"""

for i, straipsnis in enumerate(pagrindiniai_straipsniai):
    html_kodas += f"""
    <div class="article-page" id="pagrindinis_{i}">
        <div class="article-top-block">
            <div class="article-header">
                <div class="article-title">{straipsnis['title']}</div>
                <div class="article-meta"><strong>{straipsnis['author']}</strong> &nbsp;|&nbsp; <strong>Bernardinai.lt</strong> &nbsp;|&nbsp; Publikuota: {straipsnis['date']}</div>
            </div>
            {f'<img src="{straipsnis["image"]}" class="article-image">' if straipsnis['image'] else ''}
        </div>
        <div class="article-columns">
            {straipsnis['content']}
        </div>
        <div class="ad-box">
            <div class="ad-title">Čia galėtų būti Jūsų reklama</div>
            <div class="ad-contact">Kreipkitės: <a href="mailto:reklama@bernardinai.lt">reklama@bernardinai.lt</a></div>
        </div>
        <div class="back-to-toc"><a href="#turinys">↑ Grįžti į turinį</a></div>
    </div>
    """

if kiti_straipsniai:
    html_kodas += """
    <div class="other-articles-section">
        <div class="other-section-header">Kiti savaitės religijos ir tikėjimo tekstai</div>
        <div class="other-section-subtitle">Čia rasite Bernardinai.lt redaktorių ir žurnalistų atrinktas svarbiausias savaitės religinio gyvenimo bei dvasingumo naujienas, tekstus ir pokalbius.</div>
        <div class="article-columns">
    """
    for i, straipsnis in enumerate(kiti_straipsniai):
        html_kodas += f"""
            <div class="other-article" id="kitas_{i}">
                <div class="other-article-top-block">
                    <div class="other-article-title">{straipsnis['title']}</div>
                    <div class="other-article-meta">Publikuota: {straipsnis['date']}</div>
                </div>
                {straipsnis['content']}
                <div class="ad-box" style="margin-top: 25px;">
                    <div class="ad-title">Čia galėtų būti Jūsų reklama</div>
                    <div class="ad-contact">Kreipkitės: <a href="mailto:reklama@bernardinai.lt">reklama@bernardinai.lt</a></div>
                </div>
                <div class="back-to-toc"><a href="#turinys">↑ Grįžti į turinį</a></div>
            </div>
        """
    html_kodas += """
        </div>
    </div>
    """

html_kodas += f"""
    <div class="contacts-page">
        <h1 style="border-bottom: 2px solid #7a2222; padding-bottom: 10px; margin-bottom: 20px;">Redakcija ir kontaktai</h1>
        <div style="font-size: 11pt; line-height: 1.6; margin-bottom: 30px; text-align: left;">
            <strong>Interneto dienraštis „Bernardinai.lt“</strong><br>
            Veiklos pradžia – 2004 m. vasario 21 d.<br><br>
            <strong>Leidėjas:</strong> VŠĮ BERNARDINAI.LT (Bankams pradėjus tikrinti pavadinimus, prašome naudoti šį pavadinimą).<br>
            <strong>Įmonės kodas:</strong> 300671187<br>
            <strong>PVM mokėtojo kodas:</strong> LT100004414010<br>
            <strong>Sąskaitos Nr.:</strong> LT06 7044 0600 0598 4890<br>
            AB SEB bankas, Banko kodas 70440<br><br>
            <strong>Adresas:</strong> Maironio g. 10, LT-01124 Vilnius (Maironio g. 6-103)<br>
            <strong>Tel:</strong> +370 673 45416<br>
            <strong>El. paštas:</strong> redakcija@bernardinai.lt, administracija@bernardinai.lt<br>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0" style="table-layout: fixed; font-size: 10pt;">
            <tr>
                <td width="50%" valign="top" style="padding-right: 20px; border-right: 1px solid #eaeaea;">
                    <div style="font-size: 14pt; color: #111; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Redakcija</div>
                    <p><strong>Jurgita Jačėnaitė</strong><br>Vyr. redaktorė<br>jurga@bernardinai.lt</p>
                    <p><strong>Austėja Zovytė</strong><br>Vyr. redaktorės pavaduotoja<br>austeja.zovyte@bernardinai.lt</p>
                    <p><strong>Inga Bartulevičiūtė</strong><br>Visuomenės redaktorė<br>inga.bartuleviciute@bernardinai.lt</p>
                    <p><strong>Rita Bagdonaitė</strong><br>Religijos redaktorė<br>rita.bagdonaite@bernardinai.lt</p>
                    <p><strong>Vytautas Markevičius</strong><br>Žurnalistas<br>vytautas.markevicius@bernardinai.lt</p>
                    <p><strong>Austina Pakalnytė</strong><br>Žurnalistė<br>austina.pakalnyte@bernardinai.lt</p>
                    <p><strong>Ugnė Tulaitė</strong><br>Žurnalistė<br>ugne.tulaite@bernardinai.lt</p>
                    <p><strong>Austėja Žalalytė</strong><br>Žurnalistė<br>austeja.zalalyte@bernardinai.lt</p>
                    <p><strong>Laima Šiušaitė</strong><br>Dienos redaktorė<br>laima.siusaite@bernardinai.lt</p>
                </td>
                <td width="50%" valign="top" style="padding-left: 20px;">
                    <div style="font-size: 14pt; color: #111; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Bendradarbiai</div>
                    <p><strong>Darius Indrišionis</strong><br>Tekstų autorius</p>
                    <p><strong>Evgenia Levin</strong><br>Fotografė<br>el@zeneka.lt</p>
                    <p><strong>Rasa Baškienė</strong><br>Tekstų autorė<br>rasa@bernardinai.lt</p>
                    <p><strong>Gediminas Zelvaras</strong><br>Tekstų autorius<br>gediminaszelvaras22@gmail.com</p>
                    <p><strong>Saulena Žiugždaitė</strong><br>Tekstų autorė<br>saulena@bernardinai.lt</p>
                    <p><strong>Aurelija Plokštytė</strong><br>Tekstų autorė<br>aurelija.plokstyte@bernardinai.lt</p>
                    <p><strong>Teodoras Žukas</strong><br>Tekstų autorius<br>teodoras.zukas@gmail.com</p>
                    
                    <div style="font-size: 14pt; color: #111; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 20px;">Administracija</div>
                    <p><strong>Juozas Ruzgys</strong><br>Direktorius<br>juozas.ruzgys@bernardinai.lt</p>
                    <p><strong>Buhalterija</strong><br>buhalterija@bernardinai.lt</p>
                    <p><strong>Reklama</strong><br>Reklamos ir straipsnių užsakymas<br>reklama@bernardinai.lt</p>
                </td>
            </tr>
        </table>
        <div style="margin-top: 50px; text-align: center; font-size: 9pt; color: #777; border-top: 1px solid #eaeaea; padding-top: 15px;">
            © {current_year} VŠĮ BERNARDINAI.LT. Visos teisės saugomos. Griežtai draudžiama „Bernardinai.lt“ paskelbtą informaciją panaudoti kitose interneto svetainėse, žiniasklaidos priemonėse ar kitur be raštiško redakcijos sutikimo.
        </div>
    </div>
</body></html>
"""

metu_aplankas = f"archyvas/{current_year}"
os.makedirs(metu_aplankas, exist_ok=True)
pdf_archyvas = f"{metu_aplankas}/religijos_savaitrastis_{today_str}.pdf"

print(f"Generuojamas PDF failas {current_year} metų archyvui...")
try:
    HTML(string=html_kodas).write_pdf(pdf_archyvas)
    print(f">>>> Sėkmingai sukurta: {pdf_archyvas}")
except Exception as e:
    print(">>> GRIEŽTA KLAIDA GENERUOJANT PDF:")
    traceback.print_exc()
    sys.exit(1)

if is_real_run:
    try:
        with open(tracker_file, "w", encoding="utf-8") as f:
            f.write(f"{current_year}/{numeris}/{today_str}")
        print(
            ">>> TIKRAS PALEIDIMAS: Leidinio numeris atnaujintas ir"
            " išsaugotas."
        )
    except Exception as e:
        print(f"Nepavyko išsaugoti numerio failo: {e}")
else:
    if not os.path.exists(tracker_file):
        try:
            with open(tracker_file, "w", encoding="utf-8") as f:
                f.write(f"{current_year}/0/2000-01-01")
        except Exception:
            pass
    print(
        ">>> BANDOMASIS PALEIDIMAS: Naudotas 'Bandomasis' numeris, atmintis"
        " neatnaujinama."
    )

if api_key:
    print("Kuriamas ir siunčiamas MailerLite laiškas...")

    pdf_url = (
        f"https://www.bernardinai.lt/savaitrastis/{current_year}/religijos_savaitrastis_{today_str}.pdf"
    )

    email_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Religijos naujienų ir tikėjimo savaitraštis</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f4;">
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <img src="https://raw.githubusercontent.com/Bernardinai/bernardinai/main/logo.png" alt="Bernardinai.lt" style="max-width: 200px;">
        </div>
        <h1 style="text-align: center; color: #111; font-size: 24px;">Naujausias Religijos naujienų ir tikėjimo savaitraštis jau paruoštas!</h1>
        <p style="text-align: center; color: #555; font-size: 16px;">Sveiki, paruošėme jums {leidinio_data} geriausių religijos ir tikėjimo tekstų rinkinį žurnalo formatu.</p>
        
        <div style="text-align: center; margin: 40px 0;">
            <a href="{pdf_url}" style="background-color: #d32f2f; color: #ffffff; padding: 15px 30px; text-decoration: none; font-size: 18px; font-weight: bold; border-radius: 5px; display: inline-block;">Atsisiųsti PDF savaitraštį</a>
        </div>
        
        <h2 style="color: #7a2222; border-bottom: 2px solid #7a2222; padding-bottom: 10px; margin-top: 40px;">Savaitės svarbiausi</h2>
    """

    for straipsnis in pagrindiniai_straipsniai:
        email_html += f"""
        <div style="margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid #eee;">
            {f'<img src="{straipsnis["image"]}" style="width: 100%; max-width: 600px; border-radius: 8px; margin-bottom: 15px;">' if straipsnis['image'] else ''}
            <h3 style="margin: 0 0 10px 0;"><a href="{straipsnis['link']}" style="color: #111; text-decoration: none; font-size: 20px;">{straipsnis['title']}</a></h3>
            <div style="color: #7a2222; font-size: 12px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">{straipsnis['author']} | Bernardinai.lt | Publikuota: {straipsnis['date']}</div>
            <p style="color: #555; font-size: 15px; line-height: 1.5; margin: 0;">{straipsnis['excerpt']}</p>
        </div>
        """

    if kiti_straipsniai:
        email_html += """
        <h2 style="color: #7a2222; border-bottom: 2px solid #7a2222; padding-bottom: 10px; margin-top: 40px;">Kiti savaitės religijos ir tikėjimo tekstai</h2>
        <p style="color: #666; font-size: 13px; font-style: italic; margin-bottom: 20px;">Čia rasite Bernardinai.lt redaktorių ir žurnalistų atrinktas svarbiausias savaitės religinio gyvenimo bei dvasingumo naujienas, tekstus ir pokalbius.</p>
        """
        for straipsnis in kiti_straipsniai:
            email_html += f"""
            <div style="margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid #eee;">
                {f'<img src="{straipsnis["image"]}" style="width: 100%; max-width: 600px; border-radius: 8px; margin-bottom: 15px;">' if straipsnis['image'] else ''}
                <h3 style="margin: 0 0 10px 0;"><a href="{straipsnis['link']}" style="color: #111; text-decoration: none; font-size: 20px;">{straipsnis['title']}</a></h3>
                <div style="color: #7a2222; font-size: 12px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">Publikuota: {straipsnis['date']}</div>
                <p style="color: #555; font-size: 15px; line-height: 1.5; margin: 0;">{straipsnis['excerpt']}</p>
            </div>
            """

    email_html += f"""
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 12px; color: #999;">
            © {current_year} VŠĮ BERNARDINAI.LT. Visos teisės saugomos.<br>
            Išsiųsta naudojant Bernardinai.lt automatizaciją.<br><br>
            <a href="{{$url}}" style="color: #999; text-decoration: underline;">Peržiūrėti naršyklėje</a> &nbsp;|&nbsp; 
            <a href="{{$unsubscribe}}" style="color: #999; text-decoration: underline;">Atsisakyti naujienlaiškio</a>
        </div>
    </div>
</body>
</html>
"""

    payload_campaign = {
        "type": "regular",
        "groups": [103032162],
        "subject": (
            "Religijos naujienų ir tikėjimo savaitraštis |"
            f" {leidinio_data}"
        ),
        "from": "naujienlaiskis@bernardinai.lt",
        "from_name": (
            "Bernardinai.lt religijos naujienų ir tikėjimo savaitraštis"
        ),
        "language": "lt",
        "google_analytics": f"religijos-savaitrastis-{today_str}",
    }

    req_campaign = urllib.request.Request(
        "https://api.mailerlite.com/api/v2/campaigns",
        data=json.dumps(payload_campaign).encode("utf-8"),
        headers={
            "X-MailerLite-ApiKey": api_key,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req_campaign) as response:
            campaign_data = json.loads(response.read().decode("utf-8"))
            campaign_id = campaign_data.get("id")
            print(f">>> Kampanija sukurta. ID: {campaign_id}")

            if campaign_id:
                payload_content = {
                    "html": email_html,
                    "plain": (
                        "Naujausias Religijos naujienų ir tikėjimo savaitraštis"
                        " jau paruoštas!\n\nAtsisiųsti PDF galite čia:"
                        f" {pdf_url}\n\nPeržiūrėti naršyklėje:"
                        " {$url}\nAtsisakyti naujienlaiškio: {$unsubscribe}"
                    ),
                }

                req_content = urllib.request.Request(
                    f"https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/content",
                    data=json.dumps(payload_content).encode("utf-8"),
                    headers={
                        "X-MailerLite-ApiKey": api_key,
                        "Content-Type": "application/json",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                            " AppleWebKit/537.36 (KHTML, like Gecko)"
                            " Chrome/110.0.0.0 Safari/537.36"
                        ),
                    },
                    method="PUT",
                )

                with urllib.request.urlopen(req_content) as resp_content:
                    print(">>> MailerLite laiško turinys įkeltas!")

                if is_real_run:
                    req_send = urllib.request.Request(
                        f"https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/actions/send",
                        data=json.dumps({}).encode("utf-8"),
                        headers={
                            "X-MailerLite-ApiKey": api_key,
                            "Content-Type": "application/json",
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                                " AppleWebKit/537.36 (KHTML, like Gecko)"
                                " Chrome/110.0.0.0 Safari/537.36"
                            ),
                        },
                        method="POST",
                    )

                    with urllib.request.urlopen(req_send) as resp_send:
                        print(
                            ">>> TIKRAS PALEIDIMAS: MailerLite kampanija"
                            " sėkmingai perkelta į OUTBOX (pradėta siųsti)!"
                        )
                else:
                    print(
                        ">>> BANDOMASIS PALEIDIMAS: Laiškas paliktas kaip"
                        " Juodraštis (Draft)."
                    )

    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        print(
            f">>> KLAIDA kuriant MailerLite juodraštį. Kodas: {e.code},"
            f" Priežastis: {error_msg}"
        )
    except Exception as e:
        print(f">>> KLAIDA: {e}")
else:
    print(
        ">>> MAILERLITE_API_KEY nerastas aplinkoje. Juodraštis nekuriamas."
    )

# --- Sukuriame įrašą su Bernardinai.lt ACF autoriumi ir nuotrauka ---
wp_user = os.environ.get("WP_USERNAME")
wp_pass = os.environ.get("WP_APP_PASSWORD")
wp_category = int(
    os.environ.get("WP_CATEGORY_ID_RELIGIJA", 65204)
)  # Fiksuota religijos kategorija 65204
wp_acf_author_id = 8149  # Fiksuotas „Bernardinai.lt“ ACF autoriaus ID

if wp_user and wp_pass:
    print("Kuriamas informacinis įrašas Bernardinai.lt svetainėje...")

    wp_user_clean = wp_user.strip()
    wp_pass_clean = wp_pass.replace(" ", "").strip()

    print(f"Prisijungiama prie WordPress su vartotoju: '{wp_user_clean}'")

    auth_str = f"{wp_user_clean}:{wp_pass_clean}"
    encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    basic_val = f"Basic {encoded_auth}"

    wp_headers = {
        "Authorization": basic_val,
        "X-HTTP-Authorization": basic_val,
        "REDIRECT_HTTP_AUTHORIZATION": basic_val,
        "User-Agent": "Mozilla/5.0",
    }

# 1. BANDOME ĮKELTI TITULINĘ NUOTRAUKĄ Į WORDPRESS MEDIA BIBLIOTEKĄ
    featured_media_id = None
    if cover_bg_image and cover_bg_image.startswith("http"):
        try:
            svara_img_url = isvalyti_img_url(cover_bg_image)

            # Jei nuotrauka yra iš Bernardinai.lt, pašaliname galimus URL parametrus po '?'
            if "bernardinai.lt/wp-content/uploads/" in svara_img_url:
                svara_img_url = svara_img_url.split("?")[0]

            print(f"Atsisiunčiama viršelio nuotrauka iš: {svara_img_url}")
            
            # Naudojame pilną naršyklės User-Agent, kad Wordfence nelaikytų mūsų botu
            img_req = urllib.request.Request(
                svara_img_url, 
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                }
            )
            with urllib.request.urlopen(img_req) as resp:
                image_data = resp.read()

            failo_varda = f"religijos_savaitrastis_cover_{today_str}.jpg"
            media_headers = wp_headers.copy()
            media_headers["Content-Type"] = "image/jpeg"
            media_headers["Content-Disposition"] = (
                f'attachment; filename="{failo_varda}"'
            )

            req_media = urllib.request.Request(
                "https://www.bernardinai.lt/wp-json/wp/v2/media",
                data=image_data,
                headers=media_headers,
                method="POST",
            )
            with urllib.request.urlopen(req_media) as resp_media:
                media_json = json.loads(resp_media.read().decode("utf-8"))
                featured_media_id = media_json.get("id")
                print(
                    f">>> Titulinė nuotrauka sėkmingai įkelta! ID:"
                    f" {featured_media_id}"
                )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            # Jei grąžina Wordfence HTML klaidą, parodome trumpesnį pranešimą
            print(f">>> KLAIDA įkeliant nuotrauką į Media biblioteką (kodas {e.code})")
        except Exception as e:
            print(
                ">>> NEPAVYKO įkelti titulinės nuotraukos (tęsiame be jos):"
                f" {e}"
            )

    # 2. SUFORMUOJAME TRUMPĄJĄ IŠTRAUKĄ (IKI 140 SP. Ž.) IR STRAIPSNIO TURINĮ
    trumpa_istrauka = (
        "Bernardinai.lt religijos naujienų ir tikėjimo savaitraštis Nr."
        f" {leidinio_numeris}. {leidinio_data} paruoštas svarbiausių tekstų"
        " PDF rinkinys."
    )[:140]

    irasas_pavadinimas = (
        "Religijos naujienų ir tikėjimo savaitraštis Nr."
        f" {leidinio_numeris} | {leidinio_data}"
    )

    wp_html_turinys = f"""<p>Skaitytojams pateikiame interneto dienraščio „Bernardinai.lt“ Religijos naujienų ir tikėjimo savaitraščio numerį ({leidinio_data}, Nr. {leidinio_numeris}). Šiame leidinyje rasite redaktorių atrinktus svarbiausius savaitės religijos, dvasingumo bei tikėjimo tekstus ir pokalbius, paruoštus patogiam skaitymui žurnalo formatu.</p>
<p style="margin: 30px 0; text-align: center;">
    <a href="{pdf_url}" target="_blank" rel="noopener noreferrer" style="background-color: #d32f2f; color: #ffffff; padding: 14px 28px; text-decoration: none; font-weight: bold; border-radius: 5px; display: inline-block; font-size: 16px;">
        Atsisiųsti PDF savaitraštį
    </a>
</p>
<p><em>Autorius: Bernardinai.lt</em></p>"""

    payload_wp = {
        "title": irasas_pavadinimas,
        "content": wp_html_turinys,
        "excerpt": trumpa_istrauka,
        "status": "publish" if is_real_run else "draft",
        "categories": [wp_category],  # Fiksuotai 65204
        "acf": {
            "short_description": trumpa_istrauka,
            "author": [
                wp_acf_author_id
            ],  # Priskiriame 8149 jūsų ACF ryšio laukui
        },
    }

    if featured_media_id:
        payload_wp["featured_media"] = int(featured_media_id)

    post_headers = wp_headers.copy()
    post_headers["Content-Type"] = "application/json; charset=utf-8"

    req_wp = urllib.request.Request(
        "https://www.bernardinai.lt/wp-json/wp/v2/posts",
        data=json.dumps(payload_wp).encode("utf-8"),
        headers=post_headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req_wp) as resp_wp:
            wp_data = json.loads(resp_wp.read().decode("utf-8"))
            post_link = wp_data.get("link", "Nuoroda nerasta")
            print(f">>> Sėkmingai sukurtas įrašas svetainėje! URL: {post_link}")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(
            f">>> KLAIDA kuriant įrašą WordPress (kodas {e.code}):\n{err_msg}"
        )
    except Exception as e:
        print(f">>> KLAIDA kuriant WordPress įrašą: {e}")
else:
    print(
        ">>> WP_USERNAME arba WP_APP_PASSWORD nerasti aplinkoje. Įrašas"
        " svetainėje nekuriamas."
    )
