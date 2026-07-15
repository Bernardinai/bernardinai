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
# 2. RSS SRAUTŲ NUSKAITYMAS
# ==========================================
matyti_url = set()
pagrindiniai_straipsniai = []
kiti_straipsniai = []

# --- A ETAPAS: Pagrindiniai straipsniai (su nuotraukomis) iš MailerLite srauto ---
print("Nuskaitomas pagrindinis (MailerLite) RSS srautas...")
for puslapis in range(1, 10):
    rss_url = f"https://www.bernardinai.lt/?feed=mailerlite-kultura&paged={puslapis}"
    feed = feedparser.parse(rss_url)
    if not feed.entries: break

    for entry in feed.entries:
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
        pilnas_tekstas = re.sub(r'(<p[^>]*>)\s*([A-ZĄČĘĖĮŠŲŪŽa-ząčęėįšųūž])', r'\1<span class="drop-cap">\2</span>', pilnas_tekstas, count=1)

        pagrindiniai_straipsniai.append({
            'title': entry.title.replace('\n', ' ').replace('\r', '').strip(),
            'author': autorius,
            'date': data_lt,
            'image': tituline_nuotrauka,
            'content': pilnas_tekstas,
            'link': link
        })
        matyti_url.add(link)

# --- B ETAPAS: Papildomi straipsniai (be nuotraukų) iš bendro Kultūros srauto ---
print("Nuskaitomas papildomas Kultūros rubrikos RSS srautas...")
for puslapis in range(1, 10):
    rss_url = f"https://www.bernardinai.lt/kategorija/kultura/feed/?paged={puslapis}"
    feed = feedparser.parse(rss_url)
    if not feed.entries: break

    for entry in feed.entries:
        link = getattr(entry, 'link', '#')
        if link in matyti_url: continue # Praleidžiame, jei jau įdėtas kaip pagrindinis!
            
        try:
            pub_date = datetime.datetime(*entry.published_parsed[:6])
            if pub_date < one_week_ago: continue
            data_lt = f"{pub_date.year} m. {menesiai[pub_date.month - 1]} {pub_date.day} d."
        except:
            data_lt = "Data nežinoma"

        autorius = getattr(entry, 'author', 'Bernardinai.lt')
        aprasymas = getattr(entry, 'description', '')
        
        pilnas_tekstas = entry.content[0].value if (hasattr(entry, 'content') and len(entry.content) > 0) else aprasymas
        pilnas_tekstas = re.sub(r'<img[^>]*>', '', pilnas_tekstas)
        pilnas_tekstas = re.sub(r'<h([1-6])\b[^>]*>', r'<div class="heading-\1">', pilnas_tekstas, flags=re.IGNORECASE)
        pilnas_tekstas = re.sub(r'</h[1-6]>', r'</div>', pilnas_tekstas, flags=re.IGNORECASE)
        pilnas_tekstas = re.sub(r'(<p[^>]*>)\s*([A-ZĄČĘĖĮŠŲŪŽa-ząčęėįšųūž])', r'\1<span class="drop-cap">\2</span>', pilnas_tekstas, count=1)

        kiti_straipsniai.append({
            'title': entry.title.replace('\n', ' ').replace('\r', '').strip(),
            'author': autorius,
            'date': data_lt,
            'content': pilnas_tekstas,
            'link': link
        })
        matyti_url.add(link)

print(f"Iš viso atrinkta: {len(pagrindiniai_straipsniai)} pagrindinių ir {len(kiti_straipsniai)} papildomų straipsnių.")

# ==========================================
# 3. HTML IR DIZAINO GENERAVIMAS
# ==========================================
cover_bg_image = pagrindiniai_straipsniai[0]['image'] if len(pagrindiniai_straipsniai) > 0 and pagrindiniai_straipsniai[0]['image'] else ""

html_kodas = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
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
    @page cover {{ margin: 0; @bottom-center {{ content: none; }} }}
    
    body {{ font-family: 'Georgia', serif; color: #222; line-height: 1.6; font-size: 11pt; }}
    
    /* VIRŠELIS */
    .cover-page {{
        page: cover; 
        position: relative;
        width: 210mm; height: 297mm;
        background-color: #1a1a1a;
        overflow: hidden;
    }}
    .bg-img {{
        position: absolute; top: 0; left: 0; 
        width: 100%; height: 100%;
        object-fit: cover;
        z-index: 1;
    }}
    .overlay {{
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        background-color: rgba(26, 26, 26, 0.75);
        z-index: 2;
    }}
    .cover-content {{
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        text-align: center; width: 80%; color: white; z-index: 3;
    }}
    .logo-main {{ max-width: 300px; margin-bottom: 50px; filter: brightness(0) invert(1); }}
    .main-title {{ font-size: 45pt; font-weight: bold; margin-bottom: 20px; letter-spacing: 2px; text-transform: uppercase; line-height: 1.1; }}
    .sub-title {{ font-size: 18pt; color: #E0E0E0; margin-bottom: 40px; font-style: italic; }}
    .divider {{ width: 100px; height: 3px; background-color: #d32f2f; margin: 0 auto 40px auto; }}
    .meta-box {{ display: inline-block; background-color: rgba(0,0,0,0.4); padding: 20px 40px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); }}
    .meta {{ font-size: 12pt; text-transform: uppercase; letter-spacing: 1px; line-height: 1.8; }}
    
    /* TURINYS */
    .toc-page {{ page-break-before: always; }}
    .toc-title {{ text-align: center; font-size: 24pt; color: #7a2222; text-transform: uppercase; margin-bottom: 30px; margin-top: 20px; }}
    .toc-list {{ list-style: none; padding: 0; margin: 0; }}
    .toc-item {{ border-bottom: 1px dotted #ccc; margin-bottom: 15px; padding-bottom: 5px; overflow: hidden; }}
    .toc-link {{ text-decoration: none; color: #222; display: block; }}
    .toc-section-title {{ font-size: 14pt; color: #7a2222; font-weight: bold; text-transform: uppercase; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #7a2222; padding-bottom: 5px; }}
    .intro-box {{ background-color: #f9f9f9; padding: 30px; border-radius: 8px; border: 1px solid #eaeaea; margin: 50px auto; max-width: 500px; text-align: center; }}
    .btn-support {{ display: inline-block; background-color: #d32f2f; color: #FFF; padding: 10px 20px; text-decoration: none; font-weight: bold; border-radius: 4px; margin-top: 15px; }}
    
    /* STRAIPSNIAI */
    .article-page {{ page-break-before: always; }}
    .article-header {{ text-align: center; margin-bottom: 20px; }}
    .article-title {{ font-size: 26pt; font-weight: bold; margin-bottom: 10px; line-height: 1.2; }}
    .article-meta {{ font-size: 10pt; color: #666; text-transform: uppercase; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
    .article-image {{ width: 100%; max-height: 400px; object-fit: cover; margin-bottom: 25px; border-radius: 4px; }}
    .article-columns {{ column-count: 2; column-gap: 30px; text-align: justify; }}
    
    .drop-cap {{ font-size: 350%; float: left; margin: 4px 8px 0 0; color: #7a2222; line-height: 0.8; font-weight: bold; }}
    .article-columns p {{ margin-top: 0; margin-bottom: 15px; widows: 2; orphans: 2; }}
    
    /* KONTAKTAI */
    .contacts-page {{ page-break-before: always; }}
</style>
</head>
<body>

    <div class="cover-page">
        {f'<img src="{cover_bg_image}" class="bg-img">' if cover_bg_image else ''}
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
        
        <div class="toc-section-title">Savaitės tema</div>
        <ul class="toc-list">
"""

for i, straipsnis in enumerate(pagrindiniai_straipsniai):
    html_kodas += f"""
            <li class="toc-item"><a href="#pagrindinis_{i}" class="toc-link"><strong>{straipsnis['title']}</strong></a></li>"""

if kiti_straipsniai:
    html_kodas += """
        </ul>
        <div class="toc-section-title">Kiti savaitės kultūros tekstai</div>
        <ul class="toc-list">
"""
    for i, straipsnis in enumerate(kiti_straipsniai):
        html_kodas += f"""
            <li class="toc-item"><a href="#kitas_{i}" class="toc-link"><strong>{straipsnis['title']}</strong></a></li>"""

html_kodas += f"""
        </ul>
        <div class="intro-box">
            <h3 style="margin-top: 0; color: #222; font-size: 16pt;">Palaikykite mūsų veiklą</h3>
            <p style="color: #555;">Bernardinai.lt yra nepriklausomas leidinys, savo misiją tęsiantis išskirtinai skaitytojų paramos dėka. Kviečiame mus paremti.</p>
            <a href="https://www.bernardinai.lt/parama" class="btn-support">Paremkite mus</a>
        </div>
    </div>
"""

# PAGRINDINIAI STRAIPSNIAI
for i, straipsnis in enumerate(pagrindiniai_straipsniai):
    html_kodas += f"""
    <div class="article-page" id="pagrindinis_{i}">
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

# KITI SAVAITĖS STRAIPSNIAI (BE NUOTRAUKŲ)
for i, straipsnis in enumerate(kiti_straipsniai):
    html_kodas += f"""
    <div class="article-page" id="kitas_{i}">
        <div class="article-header">
            <div class="article-title">{straipsnis['title']}</div>
            <div class="article-meta">Autorius: <strong>{straipsnis['author']}</strong> &nbsp;|&nbsp; Publikuota: {straipsnis['date']}</div>
        </div>
        <div class="article-columns">
            {straipsnis['content']}
        </div>
        <div style="text-align: right; margin-top: 15px;">
            <a href="#turinys" style="color: #7a2222; text-decoration: none; font-size: 9pt;">↑ Grįžti į turinį</a>
        </div>
    </div>
    """

# DETALŪS REDAKCIJOS KONTAKTAI
html_kodas += """
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
                    <p><strong>Tomas Kemzūra</strong><br>Žurnalistas<br>tomas.kemzura@bernardinai.lt</p>
                    <p><strong>Laima Šiušaitė</strong><br>Kalbos redaktorė<br>laima.siusaite@bernardinai.lt</p>
                </td>
                <td width="50%" valign="top" style="padding-left: 20px;">
                    <div style="font-size: 14pt; color: #111; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Bendradarbiai</div>
                    <p><strong>Darius Indrišionis</strong><br>Tekstų autorius</p>
                    <p><strong>Evgenia Levin</strong><br>Fotografė<br>el@zeneka.lt</p>
                    <p><strong>Rasa Baškienė</strong><br>Tekstų autorė<br>rasa@bernardinai.lt</p>
                    <p><strong>Gediminas Zelvaras</strong><br>Tekstų autorius<br>gediminaszelvaras22@gmail.com</p>
                    <p><strong>Ugnė Tulaitė</strong><br>Tekstų autorė</p>
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
    traceback.print_exc()
    sys.exit(1)
