import sys
import traceback
import feedparser
from weasyprint import HTML
import datetime
from datetime import timedelta
import os
import re
import base64

# ==========================================
# 1. KONFIGŪRACIJA IR DATOS
# ==========================================
today = datetime.datetime.now()
one_week_ago = today - timedelta(days=7)
menesiai = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", 
            "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

leidinio_data = f"{today.year} m. {menesiai[today.month - 1]} {today.day} d."
leidinio_numeris = "1"
savaites_laikotarpis = f"{one_week_ago.year} m. {menesiai[one_week_ago.month - 1]} {one_week_ago.day} d. – {today.year} m. {menesiai[today.month - 1]} {today.day} d."

# Logotipo paruošimas
logo_src = ""
logo_failas = 'bernardinailt-main-RGB.png' 
if os.path.exists(logo_failas):
    with open(logo_failas, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        logo_src = f"data:image/png;base64,{encoded_string}"

# ==========================================
# 2. RSS SRAUTO NUSKAITYMAS
# ==========================================
print("Nuskaitomas RSS srautas...")
atrinkti_straipsniai = []
matyti_url = set()

for puslapis in range(1, 21):
    rss_url = f"https://www.bernardinai.lt/?feed=mailerlite-kultura"
    feed = feedparser.parse(rss_url)
    if not feed.entries: break

    for entry in feed.entries:
        if len(atrinkti_straipsniai) >= 15: break
        link = getattr(entry, 'link', '#')
        if link in matyti_url: continue
            
        try:
            pub_date = datetime.datetime(*entry.published_parsed[:6])
            if pub_date < one_week_ago: continue
            data_lt = f"{pub_date.year} m. {menesiai[pub_date.month - 1]} {pub_date.day} d."
        except:
            data_lt = "Data nežinoma"

        autorius = getattr(entry, 'author', 'Bernardinai.lt')
        aprasymas = getattr(entry, 'description', '')
        
        tituline_nuotrauka = ""
        paveikslelis = re.search(r'<img[^>]+src="([^">]+)"', aprasymas)
        if paveikslelis:
            tituline_nuotrauka = paveikslelis.group(1)

        pilnas_tekstas = entry.content[0].value if (hasattr(entry, 'content') and len(entry.content) > 0) else aprasymas
        pilnas_tekstas = re.sub(r'<img[^>]*>', '', pilnas_tekstas)
        pilnas_tekstas = re.sub(r'<h([1-6])\b[^>]*>', r'<div class="heading-\1">', pilnas_tekstas, flags=re.IGNORECASE)
        pilnas_tekstas = re.sub(r'</h[1-6]>', r'</div>', pilnas_tekstas, flags=re.IGNORECASE)

        atrinkti_straipsniai.append({
            'title': entry.title.replace('\n', ' ').replace('\r', '').strip(),
            'author': autorius,
            'date': data_lt,
            'image': tituline_nuotrauka,
            'content': pilnas_tekstas,
            'link': link
        })
        matyti_url.add(link)

    if len(atrinkti_straipsniai) >= 15: break

print(f"Iš viso atrinkta straipsnių: {len(atrinkti_straipsniai)}")

# ==========================================
# 3. HTML IR DIZAINO GENERAVIMAS (WEASYPRINT)
# ==========================================
cover_bg_image = atrinkti_straipsniai[0]['image'] if len(atrinkti_straipsniai) > 0 and atrinkti_straipsniai[0]['image'] else ""

html_kodas = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
    /* Modernus PDF laužymas naudojant @page */
    @page {{
        size: A4;
        margin: 20mm 15mm 20mm 15mm;
        @bottom-center {{
            content: counter(page);
            font-family: 'Georgia', serif;
            font-size: 11pt;
            color: #7a2222;
        }}
    }}
    /* Išjungiame paraštes ir puslapių numerius tik viršeliui */
    @page cover {{ margin: 0; @bottom-center {{ content: none; }} }}
    
    body {{ font-family: 'Georgia', serif; color: #222; line-height: 1.6; font-size: 11pt; }}
    
    /* 1. VIRŠELIS (Garantuotas proporcijų išlaikymas) */
    .cover-page {{
        page: cover; /* Priskiriame viršelio taisyklę */
        position: relative;
        width: 100%; height: 100vh;
        background-image: url('{cover_bg_image}');
        background-size: cover;
        background-position: center;
        background-color: #1a1a1a;
    }}
    .overlay {{
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        background-color: rgba(26, 26, 26, 0.7);
    }}
    .cover-content {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        text-align: center;
        width: 80%;
        color: white;
    }}
    .logo-main {{ max-width: 300px; margin-bottom: 50px; filter: brightness(0) invert(1); }}
    .main-title {{ font-size: 45pt; font-weight: bold; margin-bottom: 20px; letter-spacing: 2px; text-transform: uppercase; line-height: 1.1; }}
    .sub-title {{ font-size: 18pt; color: #E0E0E0; margin-bottom: 40px; font-style: italic; }}
    .divider {{ width: 100px; height: 3px; background-color: #d32f2f; margin: 0 auto 40px auto; }}
    .meta-box {{ display: inline-block; background-color: rgba(0,0,0,0.4); padding: 20px 40px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); }}
    .meta {{ font-size: 12pt; text-transform: uppercase; letter-spacing: 1px; line-height: 1.8; }}
    
    /* 2. TURINYS */
    .toc-page {{ page-break-before: always; }}
    .toc-title {{ text-align: center; font-size: 24pt; color: #7a2222; text-transform: uppercase; margin-bottom: 30px; margin-top: 20px; }}
    .toc-list {{ list-style: none; padding: 0; margin: 0; }}
    .toc-item {{ border-bottom: 1px dotted #ccc; margin-bottom: 15px; padding-bottom: 5px; overflow: hidden; }}
    .toc-link {{ text-decoration: none; color: #222; display: block; }}
    .intro-box {{ background-color: #f9f9f9; padding: 30px; border-radius: 8px; border: 1px solid #eaeaea; margin: 50px auto; max-width: 500px; text-align: center; }}
    .btn-support {{ display: inline-block; background-color: #d32f2f; color: #FFF; padding: 10px 20px; text-decoration: none; font-weight: bold; border-radius: 4px; margin-top: 15px; }}
    
    /* 3. STRAIPSNIAI (Dviejų stulpelių magija!) */
    .article-page {{ page-break-before: always; }}
    .article-header {{ text-align: center; margin-bottom: 20px; }}
    .article-title {{ font-size: 26pt; font-weight: bold; margin-bottom: 10px; line-height: 1.2; }}
    .article-meta {{ font-size: 10pt; color: #666; text-transform: uppercase; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
    
    .article-image {{ width: 100%; max-height: 400px; object-fit: cover; margin-bottom: 25px; border-radius: 4px; }}
    
    .article-columns {{
        column-count: 2;
        column-gap: 30px;
        text-align: justify;
    }}
    
    /* Graži pirmoji raidė (Drop cap) */
    .article-columns p:first-of-type::first-letter {{
        font-size: 350%; float: left; margin: 4px 8px 0 0; color: #7a2222; line-height: 0.8; font-weight: bold;
    }}
    .article-columns p {{ margin-top: 0; margin-bottom: 15px; widows: 2; orphans: 2; }}
    
    /* 4. KONTAKTAI */
    .contacts-page {{ page-break-before: always; font-size: 10pt; }}
    .contacts-grid {{ display: flex; justify-content: space-between; }}
    .col {{ width: 48%; }}
</style>
</head>
<body>

    <div class="cover-page">
        <div class="overlay"></div>
        <div class="cover-content">
            {f'<img src="{logo_src}" class="logo-main">' if logo_src else ''}
            <div class="main-title">Kultūros<br>Savaitraštis</div>
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
        <ul class="toc-list">
"""

# Generuojame turinio sąrašą su vidinėmis nuorodomis
for i, straipsnis in enumerate(atrinkti_straipsniai):
    html_kodas += f"""
            <li class="toc-item">
                <a href="#article_{i}" class="toc-link"><strong>{straipsnis['title']}</strong></a>
            </li>"""

html_kodas += f"""
        </ul>
        <div class="intro-box">
            <h3 style="margin-top: 0; color: #222; font-size: 16pt;">Palaikykite mūsų veiklą</h3>
            <p style="color: #555;">Bernardinai.lt yra nepriklausomas leidinys, savo misiją tęsiantis išskirtinai skaitytojų paramos dėka. Kviečiame mus paremti.</p>
            <a href="https://www.bernardinai.lt/parama" class="btn-support">Paremkite mus</a>
        </div>
    </div>
"""

# Generuojame straipsnius
for i, straipsnis in enumerate(atrinkti_straipsniai):
    html_kodas += f"""
    <div class="article-page" id="article_{i}">
        <div class="article-header">
            <div class="article-title">{straipsnis['title']}</div>
            <div class="article-meta">Autorius: <strong>{straipsnis['author']}</strong> &nbsp;|&nbsp; Publikuota: {straipsnis['date']}</div>
        </div>
        {f'<img src="{straipsnis["image"]}" class="article-image">' if straipsnis['image'] else ''}
        <div class="article-columns">
            {straipsnis['content']}
        </div>
        <div style="text-align: right; margin-top: 15px;">
            <a href="#turinys" style="color: #7a2222; text-decoration: none; font-size: 9pt;">↑ Grįžti į turinį</a>
        </div>
    </div>
    """

# Redakcijos kontaktai
html_kodas += """
    <div class="contacts-page">
        <h1 style="border-bottom: 2px solid #7a2222; padding-bottom: 10px;">Redakcija ir kontaktai</h1>
        <div style="margin-bottom: 30px;">
            <strong>Interneto dienraštis „Bernardinai.lt“</strong><br>
            Leidėjas: VŠĮ BERNARDINAI.LT | Įmonės kodas: 300671187 | PVM kodas: LT100004414010<br>
            Adresas: Maironio g. 10, LT-01124 Vilnius<br>
            El. paštas: redakcija@bernardinai.lt
        </div>
        <div class="contacts-grid">
            <div class="col">
                <h3 style="border-bottom: 1px solid #ccc; padding-bottom: 5px;">Redakcija</h3>
                <p><strong>Jurgita Jačėnaitė</strong> (Vyr. redaktorė)<br><strong>Austėja Zovytė</strong> (Pavaduotoja)</p>
                <p><strong>Inga Bartulevičiūtė</strong>, <strong>Rita Bagdonaitė</strong>, <strong>Vytautas Markevičius</strong>, <strong>Austina Pakalnytė</strong>, <strong>Tomas Kemzūra</strong>, <strong>Laima Šiušaitė</strong></p>
            </div>
            <div class="col">
                <h3 style="border-bottom: 1px solid #ccc; padding-bottom: 5px;">Administracija ir bendradarbiai</h3>
                <p><strong>Juozas Ruzgys</strong> (Direktorius)<br>Reklama: reklama@bernardinai.lt</p>
                <p>Bendradarbiai: D. Indrišionis, E. Levin, R. Baškienė, G. Zelvaras, U. Tulaitė, S. Žiugždaitė, A. Plokštytė, T. Žukas.</p>
            </div>
        </div>
    </div>
</body></html>
"""

# ==========================================
# 4. PDF GENERAVIMAS
# ==========================================
pdf_failas = 'kulturos_savaitrastis_zurnalas.pdf'
print("Generuojamas modernus PDF failas (WeasyPrint)...")
try:
    HTML(string=html_kodas).write_pdf(pdf_failas)
    print(f">>> Sėkmingai sukurta: {pdf_failas}")
except Exception as e:
    print(">>> GRIEŽTA KLAIDA GENERUOJANT PDF:")
    traceback.print_exc() # Ši komanda atspausdins visą vidinę klaidos anatomiją
    sys.exit(1) # Iškart sustabdo procesą, kad Github Actions parodytų raudoną klaidos kryžiuką
