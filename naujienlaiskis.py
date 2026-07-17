import sys
import traceback
import feedparser
from weasyprint import HTML
import datetime
from datetime import timedelta
import os
import re
import base64
import json
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo

event_name = os.environ.get('EVENT_NAME', '')

if event_name == 'schedule':
    lt_time = datetime.datetime.now(ZoneInfo("Europe/Vilnius"))
    if lt_time.hour != 8:
        print(f"Dabar Lietuvoje yra {lt_time.hour} val. Agentas ilsisi, nes laiškus siunčiame tik lygiai 08:00 val.")
        sys.exit(0)

today = datetime.datetime.now()
today_str = today.strftime("%Y-%m-%d")
one_week_ago = today - timedelta(days=7)
menesiai = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", 
            "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

leidinio_data = f"{today.year} m. {menesiai[today.month - 1]} {today.day} d."
savaites_laikotarpis = f"{one_week_ago.year} m. {menesiai[one_week_ago.month - 1]} {one_week_ago.day} d. – {today.year} m. {menesiai[today.month - 1]} {today.day} d."

tracker_file = 'leidinio_numeris.txt'
current_year = today.year
numeris = 1

if event_name == 'schedule':
    if os.path.exists(tracker_file):
        try:
            with open(tracker_file, 'r', encoding='utf-8') as f:
                data = f.read().strip().split('/')
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

logo_src = ""
logo_failas = 'logo.png' 
if os.path.exists(logo_failas):
    with open(logo_failas, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        logo_src = f"data:image/png;base64,{encoded_string}"

matyti_url = set()
pagrindiniai_straipsniai = []
kiti_straipsniai = []

def apdoroti_straipsni(entry, is_main=True):
    link = getattr(entry, 'link', '#')
    if link in matyti_url: return None
        
    try:
        pub_date_obj = datetime.datetime(*entry.published_parsed[:6])
        if pub_date_obj < one_week_ago: return None
        data_lt = f"{pub_date_obj.year} m. {menesiai[pub_date_obj.month - 1]} {pub_date_obj.day} d."
    except:
        pub_date_obj = datetime.datetime.now()
        data_lt = "Data nežinoma"

    saltinis = "Bernardinai.lt"
    if not is_main:
        if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
            saltinis = entry.source.title

    autorius = getattr(entry, 'author', 'Bernardinai.lt')
    aprasymas = getattr(entry, 'description', '')
    
    izanga_clean = re.sub('<[^<]+>', '', aprasymas)
    izanga_clean = izanga_clean[:250] + '...' if len(izanga_clean) > 250 else izanga_clean
    
    tituline_nuotrauka = ""
    paveikslelis = re.search(r'<img[^>]+src="([^">]+)"', aprasymas)
    if paveikslelis:
        tituline_nuotrauka = paveikslelis.group(1)

    pilnas_tekstas = entry.content[0].value if (hasattr(entry, 'content') and len(entry.content) > 0) else aprasymas
    
    if is_main:
        pilnas_tekstas = re.sub(r'<img[^>]*>', '', pilnas_tekstas)
        pilnas_tekstas = re.sub(r'<figcaption[^>]*>.*?</figcaption>', '', pilnas_tekstas, flags=re.IGNORECASE | re.DOTALL)
        pilnas_tekstas = re.sub(r'<p[^>]*class="[^"]*caption[^"]*"[^>]*>.*?</p>', '', pilnas_tekstas, flags=re.IGNORECASE | re.DOTALL)
        pilnas_tekstas = re.sub(r'<div[^>]*class="[^"]*caption[^"]*"[^>]*>.*?</div>', '', pilnas_tekstas, flags=re.IGNORECASE | re.DOTALL)
    else:
        saltinis_match = re.search(r'(?:<p>)?\s*(?:<strong>)?\s*Šaltinis\s*(?:</strong>)?\s*:\s*([^<]+)', pilnas_tekstas, re.IGNORECASE)
        if saltinis_match:
            saltinis = saltinis_match.group(1).strip()
            pilnas_tekstas = pilnas_tekstas.replace(saltinis_match.group(0), '')

    pilnas_tekstas = re.sub(r'<h([1-6])\b[^>]*>', r'<div class="heading-\1">', pilnas_tekstas, flags=re.IGNORECASE)
    pilnas_tekstas = re.sub(r'</h[1-6]>', r'</div>', pilnas_tekstas, flags=re.IGNORECASE)
    pilnas_tekstas = re.sub(r'(<p[^>]*>)\s*([A-ZĄČĘĖĮŠŲŪŽa-ząčęėįšųūž])', r'\1<span class="drop-cap">\2</span>', pilnas_tekstas, count=1)

    matyti_url.add(link)
    return {
        'title': entry.title.replace('\n', ' ').replace('\r', '').strip(),
        'author': autorius,
        'source': saltinis,
        'date': data_lt,
        'pub_date_obj': pub_date_obj,
        'image': tituline_nuotrauka,
        'excerpt': izanga_clean,
        'content': pilnas_tekstas,
        'link': link
    }

print("Nuskaitomas pagrindinis RSS srautas...")
for puslapis in range(1, 10):
    rss_url = f"https://www.bernardinai.lt/?feed=mailerlite-kultura&paged={puslapis}"
    feed = feedparser.parse(rss_url)
    if not feed.entries: break
    for entry in feed.entries:
        straipsnis = apdoroti_straipsni(entry, is_main=True)
        if straipsnis: pagrindiniai_straipsniai.append(straipsnis)

print("Nuskaitomas papildomas Kultūros RSS srautas...")
for puslapis in range(1, 10):
    rss_url = f"https://www.bernardinai.lt/kategorija/kultura/feed/?paged={puslapis}"
    feed = feedparser.parse(rss_url)
    if not feed.entries: break
    for entry in feed.entries:
        straipsnis = apdoroti_straipsni(entry, is_main=False)
        if straipsnis: kiti_straipsniai.append(straipsnis)

pagrindiniai_straipsniai.sort(key=lambda x: x['pub_date_obj'])
kiti_straipsniai.sort(key=lambda x: x['pub_date_obj'])

print(f"Iš viso atrinkta: {len(pagrindiniai_straipsniai)} pagrindinių ir {len(kiti_straipsniai)} papildomų straipsnių.")

cover_bg_image = ""
for straipsnis in reversed(pagrindiniai_straipsniai):
    if straipsnis.get('image'):
        cover_bg_image = straipsnis['image']
        break

if not cover_bg_image:
    for straipsnis in reversed(kiti_straipsniai):
        if straipsnis.get('image'):
            cover_bg_image = straipsnis['image']
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
    .cover-content {{ position: absolute; top: 48%; left: 50%; transform: translate(-50%, -50%); text-align: center; width: 85%; color: white; z-index: 3; }}
    .logo-container {{ background-color: rgba(255, 255, 255, 0.9); padding: 15px 30px; border-radius: 12px; display: inline-block; margin-bottom: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.3); }}
    .logo-main {{ max-width: 220px; display: block; }}
    .main-title {{ font-size: 42pt; font-weight: bold; margin-bottom: 15px; letter-spacing: 2px; text-transform: uppercase; line-height: 1.1; }}
    .sub-title {{ font-size: 16pt; color: #E0E0E0; margin-bottom: 30px; font-style: italic; }}
    .divider {{ width: 80px; height: 3px; background-color: #d32f2f; margin: 0 auto 30px auto; }}
    .meta-box {{ display: inline-block; background-color: rgba(0,0,0,0.5); padding: 15px 30px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); }}
    .meta {{ font-size: 9.5pt; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.8; white-space: nowrap; }}
    
    .issn-box {{ position: absolute; bottom: 15mm; right: 15mm; background-color: rgba(0,0,0,0.5); padding: 10px 20px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.2); z-index: 10; color: white; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }}
    .issn-text {{ font-size: 11pt; letter-spacing: 1px; font-weight: bold; }}
    
    .toc-page {{ page-break-before: always; padding-top: 10mm; }}
    .toc-title {{ text-align: center; font-size: 24pt; color: #7a2222; text-transform: uppercase; margin-bottom: 30px; margin-top: 20px; }}
    .toc-list {{ list-style: none; padding: 0; margin: 0; }}
    .toc-item {{ border-bottom: 1px dotted #ccc; margin-bottom: 15px; padding-bottom: 5px; overflow: hidden; }}
    .toc-link {{ text-decoration: none; color: #222; display: block; }}
    .toc-section-title {{ font-size: 14pt; color: #7a2222; font-weight: bold; text-transform: uppercase; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #7a2222; padding-bottom: 5px; }}
    .intro-box {{ background-color: #f9f9f9; padding: 30px; border-radius: 8px; border: 1px solid #eaeaea; margin: 50px auto; max-width: 500px; text-align: center; }}
    .btn-support {{ display: inline-block; background-color: #d32f2f; color: #FFF; padding: 10px 20px; text-decoration: none; font-weight: bold; border-radius: 4px; margin-top: 15px; }}
    
    .article-columns {{ column-count: 2; column-gap: 30px; text-align: justify; }}
    .drop-cap {{ font-size: 350%; float: left; margin: 4px 8px 0 0; color: #7a2222; line-height: 0.8; font-weight: bold; }}
    .article-columns p {{ margin-top: 0; margin-bottom: 15px; widows: 2; orphans: 2; }}
    
    .article-page {{ page-break-before: always; padding-top: 10mm; }}
    .article-header {{ text-align: center; margin-bottom: 20px; }}
    .article-title {{ font-size: 26pt; font-weight: bold; margin-bottom: 10px; line-height: 1.2; }}
    .article-meta {{ font-size: 10pt; color: #666; text-transform: uppercase; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
    .article-image {{ width: 100%; max-height: 400px; object-fit: cover; margin-bottom: 25px; border-radius: 4px; }}
    
    .other-articles-section {{ page-break-before: always; padding-top: 10mm; }}
    .other-section-header {{ text-align: center; font-size: 24pt; font-weight: bold; color: #7a2222; text-transform: uppercase; margin-bottom: 10px; border-bottom: 2px solid #7a2222; padding-bottom: 10px; }}
    .other-section-subtitle {{ text-align: center; font-size: 10pt; color: #666; margin-bottom: 30px; font-style: italic; padding: 0 10%; line-height: 1.5; }}
    .other-article {{ margin-bottom: 40px; }}
    .other-article-title {{ font-size: 16pt; font-weight: bold; margin-bottom: 8px; line-height: 1.2; break-after: avoid; page-break-after: avoid; color: #111; }}
    .other-article-meta {{ font-size: 9pt; color: #666; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 8px; margin-bottom: 15px; break-after: avoid; page-break-after: avoid; }}
    .other-article img {{ width: 100% !important; height: auto !important; max-height: 300px; object-fit: cover; border-radius: 4px; margin-bottom: 5px; }}
    .other-article figure, .other-article .wp-caption {{ margin: 0 0 15px 0; width: 100% !important; break-inside: avoid; page-inside: avoid; }}
    .other-article figcaption, .other-article .wp-caption-text {{ font-size: 8pt; color: #777; font-style: italic; text-align: center; line-height: 1.3; margin-top: 5px; }}
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
        
        <div class="issn-box">
            <div class="issn-text">ISSN 3120-9696</div>
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
        <div class="toc-section-title">Kiti savaitės kultūros tekstai</div>
        <ul class="toc-list">
"""
    for i, straipsnis in enumerate(kiti_straipsniai):
        html_kodas += f"""<li class="toc-item"><a href="#kitas_{i}" class="toc-link"><strong>{straipsnis['title']}</strong></a></li>"""

html_kodas += f"""
        </ul>
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
        <div class="article-header">
            <div class="article-title">{straipsnis['title']}</div>
            <div class="article-meta"><strong>{straipsnis['author']}</strong> &nbsp;|&nbsp; <strong>Bernardinai.lt</strong> &nbsp;|&nbsp; Publikuota: {straipsnis['date']}</div>
        </div>
        {f'<img src="{straipsnis["image"]}" class="article-image">' if straipsnis['image'] else ''}
        <div class="article-columns">
            {straipsnis['content']}
        </div>
        <div class="back-to-toc"><a href="#turinys">↑ Grįžti į turinį</a></div>
    </div>
    """

if kiti_straipsniai:
    html_kodas += """
    <div class="other-articles-section">
        <div class="other-section-header">Kiti savaitės kultūros tekstai</div>
        <div class="other-section-subtitle">Čia rasite Bernardinai.lt redaktorių ir žurnalistų atrinktas naujienų agentūrų BNS ir ELTA kultūros naujienas ir redakcijos gautus kitų autorių tekstus ir pranešimus spaudai apie kultūros įvykius.</div>
        <div class="article-columns">
    """
    for i, straipsnis in enumerate(kiti_straipsniai):
        html_kodas += f"""
            <div class="other-article" id="kitas_{i}">
                <div class="other-article-title">{straipsnis['title']}</div>
                <div class="other-article-meta">Publikuota: {straipsnis['date']}</div>
                {straipsnis['content']}
                <div class="back-to-toc"><a href="#turinys">↑ Grįžti į turinį</a></div>
            </div>
        """
    html_kodas += """
        </div>
    </div>
    """

html_kodas += """
    <div class="contacts-page">
        <h1 style="border-bottom: 2px solid #7a2222; padding-bottom: 10px; margin-bottom: 20px;">Redakcija ir kontaktai</h1>
        <div style="font-size: 11pt; line-height: 1.6; margin-bottom: 30px; text-align: left;">
            <strong>Interneto dienraštis „Bernardinai.lt“</strong><br>
            Veiklos pradžia – 2004 m. vasario 21 d.<br>
            <strong>ISSN 3120-9696</strong><br><br>
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

pdf_failas = 'kulturos_savaitrastis_zurnalas.pdf'
print("Generuojami PDF failai...")
try:
    HTML(string=html_kodas).write_pdf(pdf_failas)
    print(f">>>> Sėkmingai sukurta: {pdf_failas}")
except Exception as e:
    print(">>> GRIEŽTA KLAIDA GENERUOJANT PDF:")
    traceback.print_exc()
    sys.exit(1)

if event_name == 'schedule':
    try:
        with open(tracker_file, 'w', encoding='utf-8') as f:
            f.write(f"{current_year}/{numeris}/{today_str}")
        print(">>> AUTOMATINIS PALEIDIMAS: Leidinio numeris atnaujintas ir išsaugotas.")
    except Exception as e:
        print(f"Nepavyko išsaugoti numerio failo: {e}")
else:
    if not os.path.exists(tracker_file):
        try:
            with open(tracker_file, 'w', encoding='utf-8') as f:
                f.write(f"{current_year}/0/2000-01-01")
        except Exception:
            pass
    print(">>> RANKINIS PALEIDIMAS: Naudotas 'Bandomasis' numeris, atmintis neatnaujinama.")

api_key = os.environ.get('MAILERLITE_API_KEY')

if api_key:
    print("Kuriamas ir siunčiamas MailerLite laiškas...")
    
    pdf_url = "https://www.bernardinai.lt/savaitrastis/kulturos_savaitrastis_zurnalas.pdf"
    
    email_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Kultūros savaitraštis</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f4;">
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <img src="https://raw.githubusercontent.com/Bernardinai/bernardinai/main/logo.png" alt="Bernardinai.lt" style="max-width: 200px;">
        </div>
        <h1 style="text-align: center; color: #111; font-size: 24px;">Naujausias Kultūros savaitraštis jau paruoštas!</h1>
        <p style="text-align: center; color: #555; font-size: 16px;">Sveiki, paruošėme jums {leidinio_data} geriausių kultūros tekstų rinkinį žurnalo formatu.</p>
        
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
        email_html += f"""
        <h2 style="color: #7a2222; border-bottom: 2px solid #7a2222; padding-bottom: 10px; margin-top: 40px;">Kiti savaitės kultūros tekstai</h2>
        <p style="color: #666; font-size: 13px; font-style: italic; margin-bottom: 20px;">Čia rasite Bernardinai.lt redaktorių ir žurnalistų atrinktas naujienų agentūrų BNS ir ELTA kultūros naujienas ir redakcijos gautus kitų autorių tekstus ir pranešimus spaudai apie kultūros įvykius.</p>
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

    email_html += """
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 12px; color: #999;">
            <strong style="color: #444; font-size: 14px;">ISSN 3120-9696</strong><br><br>
            Išsiųsta naudojant Bernardinai.lt automatizaciją.<br><br>
            <a href="{$url}" style="color: #999; text-decoration: underline;">Peržiūrėti naršyklėje</a> &nbsp;|&nbsp; 
            <a href="{$unsubscribe}" style="color: #999; text-decoration: underline;">Atsisakyti naujienlaiškio</a>
        </div>
    </div>
</body>
</html>
"""
    
    payload_campaign = {
        "type": "regular",
        "groups": [103032162],
        "subject": f"Kultūros savaitraštis | {leidinio_data}",
        "from": "naujienlaiskis@bernardinai.lt",
        "from_name": "Bernardinai.lt kultūros savaitraštis",
        "language": "lt",
        "google_analytics": f"kulturos-savaitrastis-{today_str}"
    }
    
    req_campaign = urllib.request.Request('https://api.mailerlite.com/api/v2/campaigns', 
                                 data=json.dumps(payload_campaign).encode('utf-8'),
                                 headers={
                                     'X-MailerLite-ApiKey': api_key,
                                     'Content-Type': 'application/json',
                                     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
                                 })
    try:
        with urllib.request.urlopen(req_campaign) as response:
            campaign_data = json.loads(response.read().decode('utf-8'))
            campaign_id = campaign_data.get('id')
            print(f">>> Kampanija sukurta. ID: {campaign_id}")
            
            if campaign_id:
                payload_content = {
                    "html": email_html,
                    "plain": f"Naujausias Kultūros savaitraštis jau paruoštas!\n\nAtsisiųsti PDF galite čia: {pdf_url}\n\nISSN: 3120-9696\n\nPeržiūrėti naršyklėje: {{$url}}\nAtsisakyti naujienlaiškio: {{$unsubscribe}}"
                }
                
                req_content = urllib.request.Request(f'https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/content', 
                                     data=json.dumps(payload_content).encode('utf-8'),
                                     headers={
                                         'X-MailerLite-ApiKey': api_key,
                                         'Content-Type': 'application/json',
                                         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
                                     },
                                     method='PUT')
                
                with urllib.request.urlopen(req_content) as resp_content:
                    print(">>> MailerLite laiško turinys įkeltas!")
                    
                if event_name == 'schedule':
                    req_send = urllib.request.Request(f'https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/actions/send', 
                                         data=json.dumps({}).encode('utf-8'),
                                         headers={
                                             'X-MailerLite-ApiKey': api_key,
                                             'Content-Type': 'application/json',
                                             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
                                         },
                                         method='POST')
                    
                    with urllib.request.urlopen(req_send) as resp_send:
                        print(">>> AUTOMATINIS PALEIDIMAS: MailerLite kampanija sėkmingai perkelta į OUTBOX (pradėta siųsti)!")
                else:
                    print(">>> RANKINIS PALEIDIMAS: Laiškas paliktas kaip Juodraštis (Draft).")
                    
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        print(f">>> KLAIDA kuriant MailerLite juodraštį. Kodas: {e.code}, Priežastis: {error_msg}")
    except Exception as e:
        print(f">>> KLAIDA: {e}")
else:
    print(">>> MAILERLITE_API_KEY nerastas aplinkoje. Juodraštis nekuriamas.")
