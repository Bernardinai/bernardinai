import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

LT_TZ = ZoneInfo("Europe/Vilnius")

CF_SECRET_KEY = (
    os.environ.get("CF_AUTOMATION_KEY", "").strip()
    or "BernardinuNaujienlaiskisLabaiSlapt@00"
)
INTERNAL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    " Bernardinai-Naujienlaiskis-Bot Bernardinai-Internal-Agent-x9K2"
)

BRAND_ACCENT = "#c85a17"
BRAND_DARK = "#8f241e"
BG_PAGE = "#f4f2ef"
TEXT_MAIN = "#1f1f1f"
TEXT_MUTED = "#666666"


def kritine_klaida(pranesimas):
    print(f"\n>>> KRITINĖ APSAUGOS KLAIDA: {pranesimas}")
    print(">>> Kasdienio naujienlaiškio siuntimas SUSTABDYTAS.")
    sys.exit(1)


parser = argparse.ArgumentParser(
    description="Bernardinai.lt kasdienio 18:00 val. naujienlaiškio generatorius"
)
parser.add_argument(
    "--naujienlaiskis",
    default="",
    help="Veiksmas: juodrastis | siusti | nesiusti",
)
args, _ = parser.parse_known_args()

event_name = os.environ.get("EVENT_NAME", "").strip()
auto_18val_enabled = (
    os.environ.get("AKTYVUOTI_KASDIENI_SIUNTIMA", "ne").strip().lower()
    in ("taip", "true", "1", "yes")
)

now_lt = datetime.datetime.now(LT_TZ)

# Jei paleista pagal tvarkaraštį arba išorinį laikmatį (repository_dispatch), tikriname įjungimo vėliavėlę
if event_name in ("schedule", "repository_dispatch"):
    if not auto_18val_enabled:
        print(
            ">>> Kasdienis automatinis siuntimas dar neįjungtas"
            " (AKTYVUOTI_KASDIENI_SIUNTIMA='ne'). Procesas sustabdytas."
        )
        sys.exit(0)
    if event_name == "schedule" and now_lt.hour != 18:
        print(
            f">>> Dabar Lietuvoje {now_lt.strftime('%H:%M')} val. Laukiama"
            " tikslaus 18:00 val. lango."
        )
        sys.exit(0)

raw_nl = (
    args.naujienlaiskis or os.environ.get("SIUSTI_NAUJIENLAISKI", "")
).strip().lower()

if not raw_nl or raw_nl == "auto":
    nl_rezimas = (
        "siusti"
        if event_name in ("schedule", "repository_dispatch")
        else "juodrastis"
    )
elif raw_nl in ("siusti", "send", "true", "taip", "1"):
    nl_rezimas = "siusti"
elif raw_nl in ("juodrastis", "draft"):
    nl_rezimas = "juodrastis"
elif raw_nl in ("nesiusti", "ne", "false", "0"):
    nl_rezimas = "nesiusti"
else:
    kritine_klaida(
        f"Nežinoma SIUSTI_NAUJIENLAISKI reikšmė: '{raw_nl}'. Galimos:"
        " juodrastis, siusti, nesiusti."
    )

menesiai = [
    "sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
    "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio",
]
savaites_dienos = [
    "pirmadienis", "antradienis", "trečiadienis", "ketvirtadienis",
    "penktadienis", "šeštadienis", "sekmadienis",
]

today_str = now_lt.strftime("%Y-%m-%d")
data_antrastei = (
    f"{now_lt.year} m. {menesiai[now_lt.month - 1]} {now_lt.day} d.,"
    f" {savaites_dienos[now_lt.weekday()]}"
)
data_trumpiems = f"{now_lt.year} m. {menesiai[now_lt.month - 1]} {now_lt.day} d."

print("=================================================================")
print("LEIDINYS:       Bernardinai.lt kasdienis naujienlaiškis (Dienos temos)")
print(f"DATA:           {data_antrastei}")
print(f"REŽIMAS:        {nl_rezimas}")
print("=================================================================")

api_key = os.environ.get("MAILERLITE_API_KEY", "").strip()
if nl_rezimas in ("siusti", "juodrastis") and not api_key:
    kritine_klaida("Nerastas MAILERLITE_API_KEY aplinkos kintamasis!")

group_id = int(
    os.environ.get("MAILERLITE_GROUP_ID_KASDIENIS", "").strip()
    or os.environ.get("MAILERLITE_GROUP_ID", "").strip()
    or 103032162
)


def ar_siandien_jau_issiusta(ml_key):
    """Papildoma apsauga nuo dvigubo išsiuntimo tą pačią dieną."""
    for status_type in ("outbox", "sent"):
        try:
            req = urllib.request.Request(
                f"https://api.mailerlite.com/api/v2/campaigns/{status_type}?limit=5",
                headers={
                    "X-MailerLite-ApiKey": ml_key,
                    "Content-Type": "application/json",
                    "User-Agent": INTERNAL_USER_AGENT,
                },
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                arr = json.loads(r.read().decode("utf-8"))
                if isinstance(arr, list):
                    for c in arr:
                        mails = c.get("mails")
                        mail_subj = (
                            mails[0].get("subject", "")
                            if isinstance(mails, list)
                            and mails
                            and isinstance(mails[0], dict)
                            else ""
                        )
                        subj = str(c.get("subject") or mail_subj or c.get("name") or "")
                        created = str(c.get("date_created") or c.get("date_send") or "")
                        c_name = str(c.get("name") or "")
                        is_daily = (
                            "Bernardinai.lt šiandien:" in subj
                            or "Dienos temos:" in subj
                            or f"Kasdienis naujienlaiškis ({today_str})" in c_name
                        )
                        if (
                            is_daily
                            and "[BANDOMASIS]" not in subj
                            and "[BANDOMASIS]" not in c_name
                            and today_str in created
                        ):
                            return True
        except Exception:
            pass
    return False


if nl_rezimas == "siusti" and ar_siandien_jau_issiusta(api_key):
    print(">>> Šiandienos vakarinis naujienlaiškis jau išsiųstas! Stabdome.")
    sys.exit(0)


def uzkoduoti_url(url):
    if not url:
        return ""
    url = url.replace("&#038;", "&").replace("&amp;", "&").strip()
    # Vidinėse sekimo nuorodose (?brn_shop_go= arba ?brn_ad_click=) išsaugome originalų parametrų kodavimą ir HMAC parašą
    if "brn_shop_go=" in url or "brn_ad_click=" in url:
        return url.replace(" ", "%20")
    parts = urllib.parse.urlsplit(url)
    clean_path = urllib.parse.quote(
        urllib.parse.unquote(parts.path), safe="/:@!$&'()*+,;=-._~"
    )
    if parts.query:
        q_pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        clean_query = urllib.parse.urlencode(q_pairs, doseq=True)
    else:
        clean_query = ""
    return urllib.parse.urlunsplit(
        (parts.scheme or "https", parts.netloc, clean_path, clean_query, "")
    )


def su_kalba_ir_utm(url, lang_code):
    """Prideda automatinio vertimo parametrą ?tr=... ir naujienlaiškio UTM žymas."""
    clean = uzkoduoti_url(url) or "https://www.bernardinai.lt/"
    parts = urllib.parse.urlsplit(clean)
    q_dict = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    q_dict["tr"] = lang_code
    q_dict["utm_source"] = "mailerlite"
    q_dict["utm_medium"] = "email"
    q_dict["utm_campaign"] = f"dienos_temos_{today_str}"
    q_dict["utm_content"] = f"kalba_{lang_code}"
    return urllib.parse.urlunsplit(
        (parts.scheme or "https", parts.netloc, parts.path, urllib.parse.urlencode(q_dict), "")
    )


def email_img(raw_url, width=600, height=0, crop=True):
    """Konvertuoja WebP nuotraukas į JPG (Outlook suderinamumui), o paruoštus aštrius PNG grafinius banerius atiduoda tiesiogiai."""
    clean = uzkoduoti_url(raw_url)
    if not clean:
        clean = "https://www.bernardinai.lt/wp-content/uploads/Bernardinai500x500-jpg-webp.webp"
    # Mūsų el. paštui sugeneruoti PNG baneriai ir Gymglish kortelės jau yra lengvi .png failai – nesiunčiame per JPG glaudinimą, kad tekstas liktų ryškus
    if ("/brn-nl-assets/" in clean or "/nl-asset/" in clean) and clean.lower().endswith(".png"):
        return clean
    be_schemos = re.sub(r"^https?://", "", clean, flags=re.I)
    params = f"url={urllib.parse.quote(be_schemos, safe='')}&output=jpg&w={width}&q=85"
    if height > 0:
        fit_mode = "cover" if crop else "contain&bg=white"
        params += f"&h={height}&fit={fit_mode}"
    return f"https://images.weserv.nl/?{params}"


def esc(text):
    return html.escape(str(text or "").strip())


def su_utm(url, saltinis_blokas):
    clean = uzkoduoti_url(url)
    if not clean:
        return "https://www.bernardinai.lt/"
    # Jei tai jau vidinė sekimo nuoroda (?brn_ad_click arba ?brn_shop_go), jos nekeičiame
    if "brn_ad_click=" in clean or "brn_shop_go=" in clean:
        return clean
    sep = "&" if "?" in clean else "?"
    return (
        f"{clean}{sep}utm_source=mailerlite&utm_medium=email"
        f"&utm_campaign=dienos_temos_{today_str}&utm_content={saltinis_blokas}"
    )


def gauti_duomenis_is_wp_api():
    endpoint = f"https://www.bernardinai.lt/wp-json/custom/v1/daily-newsletter?_t={int(datetime.datetime.now().timestamp())}"
    req = urllib.request.Request(
        endpoint,
        headers={
            "User-Agent": INTERNAL_USER_AGENT,
            "X-Bnd-Automate": CF_SECRET_KEY,
            "Referer": "https://www.bernardinai.lt/",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "main_posts" in data:
                print(">>> Duomenys sėkmingai gauti iš /wp-json/custom/v1/daily-newsletter!")
                return data
    except urllib.error.HTTPError as e:
        print(
            f">>> Pastaba: specialus WP įskiepio adresas neatsakė (HTTP {e.code})."
            " Naudojamas atsarginis standartinis WP REST API."
        )
    except Exception as e:
        print(
            f">>> Pastaba: nepavyko pasiekti specialaus WP mazgo ({e})."
            " Naudojamas atsarginis standartinis WP REST API."
        )
    return None


def pazymeti_issiustus_straipsnius_wp(post_ids, quote_hash=""):
    """Tik po tikro išsiuntimo pažymi straipsnių ID ir citatą WordPress duomenų bazėje, kad kitą dieną nesikartotų."""
    if not post_ids and not quote_hash:
        return
    endpoint = "https://www.bernardinai.lt/wp-json/custom/v1/daily-newsletter/mark-sent"
    payload = json.dumps({"post_ids": post_ids, "quote_hash": quote_hash}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "User-Agent": INTERNAL_USER_AGENT,
            "X-Bnd-Automate": CF_SECRET_KEY,
            "Referer": "https://www.bernardinai.lt/",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))
            print(
                f">>> Panaudoti straipsniai įsiminti WordPress bazėje"
                f" (naujų: {res.get('saved_count', 0)}, viso saugoma: {res.get('total_kept', 0)})."
            )
    except Exception as e:
        print(f">>> Pastaba: nepavyko įrašyti išsiųstų ID į WP atmintį ({e}).")


def isvalyti_html_teksta(raw_html, max_len=200):
    txt = html.unescape(re.sub(r"<[^>]+>", " ", str(raw_html or "")))
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > max_len:
        return txt[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return txt


def gauti_atsarginius_duomenis_standartiniu_api():
    headers = {
        "User-Agent": INTERNAL_USER_AGENT,
        "X-Bnd-Automate": CF_SECRET_KEY,
        "Referer": "https://www.bernardinai.lt/",
        "Accept": "application/json",
    }
    used_ids = set()
    after_iso = (now_lt - datetime.timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%S")

    def fetch_posts(params_str, limit=5):
        u = f"https://www.bernardinai.lt/wp-json/wp/v2/posts?{params_str}&after={after_iso}&_embed=1"
        req = urllib.request.Request(u, headers=headers)
        items = []
        with urllib.request.urlopen(req, timeout=25) as r:
            arr = json.loads(r.read().decode("utf-8"))
            for p in arr:
                pid = p.get("id")
                if not pid or pid in used_ids:
                    continue
                title = isvalyti_html_teksta(p.get("title", {}).get("rendered", ""), 220)
                if "savaitraštis nr." in title.lower():
                    continue
                excerpt = isvalyti_html_teksta(
                    p.get("acf", {}).get("short_description", "")
                    or p.get("excerpt", {}).get("rendered", ""),
                    190,
                )
                img = p.get("featured_image_src", "")
                if not img:
                    media = p.get("_embedded", {}).get("wp:featuredmedia", [])
                    if media and isinstance(media[0], dict):
                        img = media[0].get("source_url", "")
                used_ids.add(pid)
                items.append(
                    {
                        "id": pid,
                        "title": title,
                        "link": p.get("link", ""),
                        "excerpt": excerpt,
                        "image": img,
                        "author": "Bernardinai.lt",
                        "author_avatar": "",
                        "poster_label": "",
                    }
                )
                if len(items) >= limit:
                    break
        return items

    main_posts = fetch_posts("per_page=8", limit=5)
    rubrikos_cfg = [
        (16, "religija", "Religija", "https://www.bernardinai.lt/kategorija/religija/"),
        (17, "visuomene", "Visuomenė", "https://www.bernardinai.lt/kategorija/visuomene/"),
        (18, "kultura", "Kultūra", "https://www.bernardinai.lt/kategorija/kultura/"),
        (19, "seima", "Šeima", "https://www.bernardinai.lt/kategorija/seima/"),
        (39794, "dialogai", "Dialogai", "https://www.bernardinai.lt/kategorija/dialogo-erdve/"),
    ]
    categories = []
    for cid, slug, title, curl in rubrikos_cfg:
        citems = fetch_posts(f"categories={cid}&per_page=6", limit=2)
        if citems:
            categories.append({"title": title, "slug": slug, "url": curl, "items": citems})

    return {
        "quote": None,
        "main_posts": main_posts,
        "editorials": [],
        "most_read": [],
        "categories": categories,
        "posters": [],
        "direct_ad": None,
        "partner_showcase": None,
        "issue_post_ids": list(used_ids),
    }


duomenys = gauti_duomenis_is_wp_api()
if not duomenys:
    duomenys = gauti_atsarginius_duomenis_standartiniu_api()

main_posts = duomenys.get("main_posts") or []
if len(main_posts) < 1:
    print(">>> Šiandien naujų dar neišsiųstų viršinių straipsnių nerasta. Laiškas nesiunčiamas.")
    sys.exit(0)

quote = duomenys.get("quote")
editorials = duomenys.get("editorials") or []
most_read = duomenys.get("most_read") or []
categories = duomenys.get("categories") or []
posters = duomenys.get("posters") or []
direct_ad = duomenys.get("direct_ad")
partner_showcase = duomenys.get("partner_showcase")
issue_post_ids = duomenys.get("issue_post_ids") or []

print(
    f">>> Surinkta: {len(main_posts)} viršiniai, {len(editorials)} komentarai,"
    f" {len(most_read)} skaitomiausi, {len(categories)} rubrikos,"
    f" {len(posters)} afišos anonsai, citata: {'TAIP' if quote else 'NE'},"
    f" užsakovo baneris: {'TAIP' if direct_ad else 'NE'},"
    f" partnerių vitrina: {partner_showcase.get('id') if isinstance(partner_showcase, dict) else 'NE'}."
)


# =========================================================================
# LAIŠKO TEMOS (SUBJECT) FORMAVIMAS: REDAKCINIS DI + ŠVARUS ATSARGINIS
# =========================================================================
def isvalyti_viena_antraste_temai(antraste):
    """Paruošia tikrą redakcijos antraštę be dirbtinio karpymo ir gramatikos laužymo."""
    t = re.sub(r"\s+", " ", str(antraste or "")).strip()
    if not t:
        return ""
    # Nuimame tik išorinius brūkšnius pačioje pradžioje/pabaigoje, bet paliekame vidines kabutes „...“ ir klaustukus!
    t = re.sub(r"^[\-–—\s]+|[\-–—\s]+$", "", t).strip()
    # Jei antraštėje yra dvitaškis (pvz., „Autorius: tikroji antraštė“) ir visa eilutė per ilga – imame dalį po dvitaškio
    if ":" in t and len(t) > 62:
        kaire, desine = [d.strip() for d in t.split(":", 1)]
        desine_clean = re.sub(r'^[„"«\s]+|[“"»\s]+$', "", desine).strip()
        if len(desine_clean) >= 18:
            t = desine_clean[0].upper() + desine_clean[1:]
    # Pašaliname tik tašką gale (paliekant ? arba !)
    t = t.rstrip(".")
    return t


def isskirti_temos_akcenta(antraste, max_ilgis=42):
    """Atsarginis trumpiklis antrajai temai – tik jei frazė natūraliai trumpa ir be dviprasmiškų jungtukų."""
    t = re.sub(r"\s+", " ", str(antraste or "")).strip()
    if not t:
        return ""
    if ":" in t:
        kaire, desine = [d.strip() for d in t.split(":", 1)]
        kaire_be_kab = re.sub(r'[„“"\']', "", kaire).strip()
        desine_be_kab = re.sub(r'^[„"«\s]+|[“"»\s]+$', "", desine).strip()
        has_initials = bool(re.search(r"\b[A-ZĄČĘĖĮŠŲŪŽ]\.\s*[A-ZĄČĘĖĮŠŲŪŽ]", kaire))
        if not has_initials and 10 <= len(kaire_be_kab) <= max_ilgis and "?" not in kaire_be_kab:
            kandidatas = kaire_be_kab
        else:
            kandidatas = desine_be_kab
    else:
        kandidatas = t

    kandidatas = re.sub(r'^[„"«\s]+|[“"».,;:\-–—\s]+$', "", kandidatas).strip()
    if len(kandidatas) > max_ilgis:
        return ""
    return kandidatas


def ar_tema_kokybiska(cand_txt):
    """Patikrina, ar DI sugeneruota eilutė neturi kalbos šiukšlių, dvigubų 'ir' ar klišių."""
    if not cand_txt.startswith("Bernardinai.lt šiandien: "):
        return False
    if "..." in cand_txt or "…" in cand_txt or '"' in cand_txt:
        return False
    if not (42 <= len(cand_txt) <= 92):
        return False
    po_dvitaskio = cand_txt[len("Bernardinai.lt šiandien: ") :].strip()
    if ":" in po_dvitaskio:
        return False
    # Neleidžiame pasikartojančių „ir ... ir ...“
    if len(re.findall(r"\bir\b", po_dvitaskio.lower())) > 1:
        return False
    draudziami = (
        "kviečiame", "nepraleiskite", "sužinokite", "įkvepian",
        "gilinamės", "apžvelgiame", "skaitykite", "šiame numeryje",
    )
    if any(d in po_dvitaskio.lower() for d in draudziami):
        return False
    return True


def sugeneruoti_laisko_tema_su_di(main_list, ed_list):
    """Suformuluoja santūrią, taisyklingos lietuvių kalbos redakcinę temą (tik jei aplinkoje yra API raktas)."""
    rinkinys = list(main_list[:4]) + list(ed_list[:2])
    antrastes = []
    for s in rinkinys:
        ttl = (s.get("title") or "").strip()
        exc = (s.get("excerpt") or "").strip()
        if ttl:
            antrastes.append(f"- Antraštė: {ttl}" + (f" (Kontekstas: {exc[:110]})" if exc else ""))
    if not antrastes:
        return ""

    prompt = (
        "Esi reiklus interneto dienraščio „Bernardinai.lt“ kalbos redaktorius. "
        "Pagal šios dienos pagrindinius tekstus parašyk VIENĄ el. laiško temos eilutę (Subject).\n\n"
        "GRIEŽTI KALBOS IR STILIAUS REIKALAVIMAI:\n"
        "1. Privalo prasidėti tiksliai taip: Bernardinai.lt šiandien: \n"
        "2. Stilius – santūrus, intelektualus, žurnalistinis, be menkiausio dirbtinio intelekto ar reklamos atspalvio.\n"
        "3. Pasirink 2 svarbiausias dienos temas ir suformuluok jas kaip glaudžius, gramatiškai suderintus vardinius junginius "
        "(atsakant į klausimą „kas?“ arba „apie ką?“), atskirtus KABLIATAŠKIU (; ) arba vienu jungtuku „ir“.\n"
        "4. GRIEŽTAI DRAUDŽIAMA mechaniškai suklijuoti du nesuderintus sakinius ar klausimus, vartoti žodį „ir“ daugiau nei vieną kartą, "
        "naudoti antrą dvitaškį, daugtaškius (...) ar kanceliarines/reklamines klišes („apžvelgiame“, „kviečiame“, „įkvepiantis“, „aktualijos“).\n"
        "5. Nepriekaištinga lietuvių kalba: lietuviškos kabutės „...“, taisyklinga didžiųjų raidžių rašyba (Dievas, Bažnyčia, Šventasis Raštas, Visatos Valdovas, valstybių ir asmenų vardai). "
        "Pirmasis žodis po „Bernardinai.lt šiandien: “ rašomas mažąja raide, nebent tai tikrinis vardas.\n"
        "6. Visos eilutės ilgis (su pradžia) – nuo 50 iki 84 simbolių. Gale nedėk taško.\n"
        "7. Grąžink TIK pačią vieną eilutę be jokių paaiškinimų.\n\n"
        "Gero stiliaus pavyzdžiai:\n"
        "Bernardinai.lt šiandien: Kristaus Karaliaus iškilmė ir pokalbis apie gyvą pamokslą\n"
        "Bernardinai.lt šiandien: derybos dėl Ukrainos saugumo; kaip nepavargti nuo informacinio triukšmo\n"
        "Bernardinai.lt šiandien: pokyčiai švietimo sistemoje ir nauja paroda Nacionalinėje galerijoje\n\n"
        "Šiandienos straipsniai:\n" + "\n".join(antrastes)
    )

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
            try:
                g_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                g_body = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300, "thinkingConfig": {"thinkingBudget": 0}},
                }
                req = urllib.request.Request(
                    g_url,
                    data=json.dumps(g_body).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as r:
                    resp_json = json.loads(r.read().decode("utf-8"))
                    cand_txt = (
                        resp_json.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                        .strip()
                    )
                    cand_txt = cand_txt.splitlines()[0].strip().strip('"„“').rstrip(".")
                    if ar_tema_kokybiska(cand_txt):
                        print(f">>> Tema suformuluota su DI ({model_name}).")
                        return cand_txt
            except Exception as e:
                print(f">>> Pastaba: Gemini temos generavimas praleistas ({model_name}: {e}).")

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        try:
            o_body = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 90,
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(o_body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                resp_json = json.loads(r.read().decode("utf-8"))
                cand_txt = (
                    resp_json.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                cand_txt = cand_txt.splitlines()[0].strip().strip('"„“').rstrip(".")
                if ar_tema_kokybiska(cand_txt):
                    print(">>> Tema suformuluota su DI (OpenAI).")
                    return cand_txt
        except Exception as e:
            print(f">>> Pastaba: OpenAI temos generavimas praleistas ({e}).")

    return ""


def suformuoti_laisko_tema(main_list, ed_list, cat_list, data_trumpa):
    """Garantuoja taisyklingą temą: pirma bando kalbos redaktoriaus DI, o jei nėra rakto – naudoja švarią pagrindinę antraštę be dirbtinio 'ir'."""
    di_tema = sugeneruoti_laisko_tema_su_di(main_list, ed_list)
    if di_tema:
        return di_tema

    pradzia = "Bernardinai.lt šiandien: "
    visi = list(main_list) + list(ed_list)

    # ATSARGINIS VARIANTAS BE DI (100 % žmogaus rašyta redakcijos kalba, jokių suklijavimų per „ir“!):
    # 1. Jei pagrindinio dienos straipsnio („Hero“) antraštė telpa – rodome ją autentišką ir neiškraipytą
    if visi:
        hero_clean = isvalyti_viena_antraste_temai(visi[0].get("title", ""))
        if 15 <= len(hero_clean) <= 68:
            # Jei pirmoji labai trumpa (iki 34 simb.), per kabliataškį pridedame antrąją trumpą temą
            if len(hero_clean) <= 34 and len(visi) > 1:
                antras = isskirti_temos_akcenta(visi[1].get("title", ""), max_ilgis=34)
                if antras and antras.lower() != hero_clean.lower():
                    antras_fmt = (
                        antras[0].lower() + antras[1:]
                        if not antras[0].isupper() or len(antras.split()[0]) > 2
                        else antras
                    )
                    junginys = f"{pradzia}{hero_clean}; {antras_fmt}"
                    if len(junginys) <= 92:
                        return junginys
            return f"{pradzia}{hero_clean}"

    # 2. Jei pirmoji antraštė itin ilga – ieškome bet kurios kitos neapkarpytos viršinės antraštės
    for st in visi[1:5]:
        st_clean = isvalyti_viena_antraste_temai(st.get("title", ""))
        if 18 <= len(st_clean) <= 66:
            return f"{pradzia}{st_clean}"

    return f"Bernardinai.lt šiandien: svarbiausi {data_trumpa} tekstai ir komentarai"


# =========================================================================
# EL. LAIŠKO HTML FORMAVIMAS (600px, PRITAIKYTA MOBILIESIEMS IR OUTLOOK)
# =========================================================================
hero = main_posts[0]
secondary_main = main_posts[1:]

html_parts = []
html_parts.append(f"""<!DOCTYPE html>
<html lang="lt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bernardinai.lt – Dienos temos</title>
<style>
  @media only screen and (max-width: 620px) {{
    .wrapper {{ width: 100% !important; }}
    .mobile-stack {{ display: block !important; width: 100% !important; padding-left: 0 !important; padding-right: 0 !important; }}
    .mobile-img {{ width: 100% !important; height: auto !important; margin-bottom: 12px !important; }}
    .content-pad {{ padding-left: 16px !important; padding-right: 16px !important; }}
    .btn-col {{ display: block !important; width: 100% !important; margin-bottom: 8px !important; }}
    .prod-col {{ display: block !important; width: 100% !important; padding: 0 0 12px 0 !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; background-color:{BG_PAGE}; font-family: Arial, Helvetica, sans-serif; color:{TEXT_MAIN}; -webkit-font-smoothing:antialiased;">
<div style="display:none; max-height:0; overflow:hidden; opacity:0;">
  {esc(" • ".join([p.get("title", "") for p in (main_posts[:3] + editorials[:1]) if p.get("title")]))}
</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{BG_PAGE}; padding: 20px 0;">
  <tr>
    <td align="center">
      <table role="presentation" class="wrapper" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px; max-width:600px; background-color:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.05);">

        <!-- VIRŠUTINĖ JUOSTA IR LOGOTIPAS -->
        <tr>
          <td class="content-pad" style="padding: 22px 28px 18px 28px; border-bottom: 3px solid {BRAND_ACCENT}; background-color:#ffffff;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td valign="middle" align="left">
                  <a href="{su_utm('https://www.bernardinai.lt/', 'header_logo')}" target="_blank" style="text-decoration:none;">
                    <img src="https://raw.githubusercontent.com/Bernardinai/bernardinai/main/logo.png" alt="Bernardinai.lt" width="185" style="display:block; max-width:185px; height:auto; border:0;">
                  </a>
                </td>
                <td valign="middle" align="right" style="font-family: Georgia, serif; text-align:right;">
                  <div style="font-size:16px; font-weight:bold; color:{TEXT_MAIN};">Dienos temos</div>
                  <div style="font-size:12px; color:{TEXT_MUTED}; margin-top:3px;">{esc(data_antrastei)}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
""")

# 1. DIENOS CITATA (RODOMA TIK JEI DAR NEBUVO SIŲSTA)
if isinstance(quote, dict) and quote.get("text"):
    q_link = su_utm(quote["link"], "dienos_citata") if quote.get("link") else ""
    q_text_html = esc(quote["text"])
    if q_link:
        q_text_html = f'<a href="{q_link}" target="_blank" style="color:{TEXT_MAIN}; text-decoration:none;">{q_text_html}</a>'
    q_author = esc(quote.get("author", ""))

    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 22px 28px 6px 28px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#faf6f2; border-left:4px solid {BRAND_ACCENT}; border-radius:4px;">
              <tr>
                <td style="padding: 16px 20px;">
                  <div style="font-size:11px; font-weight:bold; text-transform:uppercase; letter-spacing:1.2px; color:{BRAND_ACCENT}; margin-bottom:6px;">Dienos citata</div>
                  <div style="font-family: Georgia, serif; font-size:16px; font-style:italic; line-height:1.55; color:{TEXT_MAIN};">„{q_text_html}“</div>
                  {f'<div style="font-size:13px; font-weight:bold; color:#444444; margin-top:8px;">— {q_author}</div>' if q_author else ''}
                </td>
              </tr>
            </table>
          </td>
        </tr>
    """)

# 2. PAGRINDINĖ DIENOS TEMA (IŠMANIAI ATRINKTA PAGAL SKAITOMUMĄ TARP ŠIANDIENOS VIRŠINIŲ)
hero_url = su_utm(hero.get("link"), "pagrindine_tema")
hero_img = email_img(hero.get("image"), width=600, height=340)
html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 24px 28px 20px 28px;">
            <div style="font-size:11px; font-weight:bold; text-transform:uppercase; letter-spacing:1.2px; color:{BRAND_ACCENT}; margin-bottom:10px;">Pagrindinė dienos tema</div>
            <a href="{hero_url}" target="_blank" style="text-decoration:none;">
              <img src="{hero_img}" alt="{esc(hero.get('title'))}" width="544" style="display:block; width:100%; max-width:544px; height:auto; border-radius:6px; border:0; margin-bottom:14px;">
            </a>
            <div style="font-size:12px; font-weight:bold; color:{TEXT_MUTED}; text-transform:uppercase; margin-bottom:6px;">{esc(hero.get('author', 'Bernardinai.lt'))}</div>
            <h1 style="font-family: Georgia, serif; font-size:23px; line-height:1.3; margin:0 0 10px 0; font-weight:bold;">
              <a href="{hero_url}" target="_blank" style="color:{TEXT_MAIN}; text-decoration:none;">{esc(hero.get('title'))}</a>
            </h1>
            <p style="font-size:15px; line-height:1.55; color:#444444; margin:0 0 14px 0;">{esc(hero.get('excerpt'))}</p>
            <a href="{hero_url}" target="_blank" style="display:inline-block; background-color:{BRAND_ACCENT}; color:#ffffff; font-size:13px; font-weight:bold; text-decoration:none; padding:9px 18px; border-radius:4px;">Skaityti straipsnį →</a>
          </td>
        </tr>
""")

# KITI SVARBIAUSI VIRŠINIAI STRAIPSNIAI (AKTUALIJOS)
if secondary_main:
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 8px 28px 16px 28px;">
            <div style="border-top:2px solid #ececec; padding-top:18px; margin-bottom:14px; font-family: Georgia, serif; font-size:19px; font-weight:bold; color:{TEXT_MAIN};">Svarbiausios aktualijos</div>
    """)
    for idx, item in enumerate(secondary_main):
        i_url = su_utm(item.get("link"), f"aktualijos_{idx+1}")
        i_img = email_img(item.get("image"), width=320, height=210)
        border_style = "border-bottom:1px solid #efefef; padding-bottom:16px; margin-bottom:16px;" if idx < len(secondary_main) - 1 else ""
        html_parts.append(f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="{border_style}">
              <tr>
                <td class="mobile-stack" width="165" valign="top" style="width:165px; padding-right:16px;">
                  <a href="{i_url}" target="_blank" style="text-decoration:none;">
                    <img class="mobile-img" src="{i_img}" alt="{esc(item.get('title'))}" width="165" style="display:block; width:165px; height:auto; border-radius:5px; border:0;">
                  </a>
                </td>
                <td class="mobile-stack" valign="top">
                  <div style="font-size:11px; font-weight:bold; color:{BRAND_ACCENT}; text-transform:uppercase; margin-bottom:4px;">{esc(item.get('author', 'Bernardinai.lt'))}</div>
                  <div style="font-family: Georgia, serif; font-size:16px; font-weight:bold; line-height:1.35; margin-bottom:6px;">
                    <a href="{i_url}" target="_blank" style="color:{TEXT_MAIN}; text-decoration:none;">{esc(item.get('title'))}</a>
                  </div>
                  <div style="font-size:13px; line-height:1.45; color:#555555;">{esc(item.get('excerpt'))}</div>
                </td>
              </tr>
            </table>
        """)
    html_parts.append("          </td>\n        </tr>")

# TIESIOGINĖ UŽSAKOVO REKLAMA IŠ „📢 REKLAMOS VALDYMAS“ (JEI ŠIUO METU YRA AKTYVI UŽSAKOVO KAMPANIJA)
if isinstance(direct_ad, dict) and direct_ad.get("image") and direct_ad.get("click_url"):
    ad_img = email_img(direct_ad["image"], width=600)
    ad_click = uzkoduoti_url(direct_ad["click_url"])
    ad_lbl = esc(direct_ad.get("label") or "Reklama")
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 8px 28px 18px 28px;">
            <div style="font-size:10px; text-transform:uppercase; letter-spacing:1px; color:#999999; text-align:center; margin-bottom:5px;">{ad_lbl}</div>
            <a href="{ad_click}" target="_blank" rel="noopener sponsored" style="text-decoration:none;">
              <img src="{ad_img}" alt="{esc(direct_ad.get('client') or direct_ad.get('title') or 'Reklama')}" width="544" style="display:block; width:100%; max-width:544px; height:auto; border-radius:6px; border:0;">
            </a>
          </td>
        </tr>
    """)

# 3. NUOMONĖS IR KOMENTARAI (TIK JEI YRA NAUJŲ, DAR NESIŲSTŲ TEKSTŲ)
if editorials:
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 16px 28px 20px 28px; background-color:#faf8f5; border-top:1px solid #eee7de; border-bottom:1px solid #eee7de;">
            <div style="font-family: Georgia, serif; font-size:19px; font-weight:bold; color:{BRAND_DARK}; margin-bottom:14px;">Komentarai ir įžvalgos</div>
    """)
    for idx, ed in enumerate(editorials):
        e_url = su_utm(ed.get("link"), f"komentaras_{idx+1}")
        av_raw = ed.get("author_avatar") or ed.get("image")
        av_img = email_img(av_raw, width=112, height=112)
        b_style = "border-bottom:1px solid #eae3da; padding-bottom:12px; margin-bottom:12px;" if idx < len(editorials) - 1 else ""
        html_parts.append(f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="{b_style}">
              <tr>
                <td width="56" valign="top" style="width:56px; padding-right:14px;">
                  <a href="{e_url}" target="_blank" style="text-decoration:none;">
                    <img src="{av_img}" alt="{esc(ed.get('author'))}" width="52" height="52" style="display:block; width:52px; height:52px; border-radius:50%; object-fit:cover; border:2px solid {BRAND_ACCENT};">
                  </a>
                </td>
                <td valign="middle">
                  <div style="font-size:11px; font-weight:bold; text-transform:uppercase; color:{BRAND_ACCENT}; margin-bottom:3px;">{esc(ed.get('author'))}</div>
                  <div style="font-family: Georgia, serif; font-size:16px; font-weight:bold; line-height:1.35;">
                    <a href="{e_url}" target="_blank" style="color:{TEXT_MAIN}; text-decoration:none;">{esc(ed.get('title'))}</a>
                  </div>
                </td>
              </tr>
            </table>
        """)
    html_parts.append("          </td>\n        </tr>")

# 4. SKAITOMIAUSI TEKSTAI (BE DUBLIKATŲ SU VAKARYKŠČIAIS)
if most_read:
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 20px 28px 10px 28px;">
            <div style="font-family: Georgia, serif; font-size:19px; font-weight:bold; color:{TEXT_MAIN}; margin-bottom:12px; border-bottom:2px solid {BRAND_ACCENT}; padding-bottom:6px;">Skaitomiausi tekstai</div>
    """)
    for idx, mr in enumerate(most_read, start=1):
        m_url = su_utm(mr.get("link"), f"skaitomiausi_{idx}")
        html_parts.append(f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px;">
              <tr>
                <td width="34" valign="top" style="font-family: Georgia, serif; font-size:24px; font-weight:bold; color:{BRAND_ACCENT}; line-height:1.1;">{idx}.</td>
                <td valign="top">
                  <a href="{m_url}" target="_blank" style="font-family: Georgia, serif; font-size:15px; font-weight:bold; color:{TEXT_MAIN}; text-decoration:none; line-height:1.35;">{esc(mr.get('title'))}</a>
                  <div style="font-size:11px; color:{TEXT_MUTED}; margin-top:2px;">{esc(mr.get('author', 'Bernardinai.lt'))}</div>
                </td>
              </tr>
            </table>
        """)
    html_parts.append("          </td>\n        </tr>")

# 5. RUBRIKŲ APŽVALGA (RODOMOS TIK TOS RUBRIKOS, KURIOSE YRA NAUJŲ TEKSTŲ)
if categories:
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 18px 28px 8px 28px;">
            <div style="font-family: Georgia, serif; font-size:20px; font-weight:bold; color:{TEXT_MAIN}; margin-bottom:14px;">Rubrikų apžvalga</div>
    """)
    for cat in categories:
        cat_title = esc(cat.get("title"))
        cat_url = su_utm(cat.get("url") or "https://www.bernardinai.lt/", f"rubrika_{cat.get('slug', 'kita')}")
        c_items = cat.get("items") or []
        if not c_items:
            continue
        html_parts.append(f"""
            <div style="margin-bottom:20px; background-color:#fcfcfb; border:1px solid #eeeeee; border-radius:6px; padding:14px 16px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:10px; border-bottom:1px solid #eaeaea; padding-bottom:6px;">
                <tr>
                  <td align="left" style="font-size:13px; font-weight:bold; text-transform:uppercase; letter-spacing:1px; color:{BRAND_ACCENT};">{cat_title}</td>
                  <td align="right"><a href="{cat_url}" target="_blank" style="font-size:12px; color:{TEXT_MUTED}; text-decoration:none;">Visi tekstai →</a></td>
                </tr>
              </table>
        """)
        for c_idx, ci in enumerate(c_items):
            ci_url = su_utm(ci.get("link"), f"rubrika_{cat.get('slug')}_{c_idx+1}")
            ci_img = email_img(ci.get("image"), width=180, height=120)
            row_pad = "padding-bottom:10px; margin-bottom:10px; border-bottom:1px dotted #e5e5e5;" if c_idx < len(c_items) - 1 else ""
            html_parts.append(f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="{row_pad}">
                <tr>
                  <td width="92" valign="top" style="width:92px; padding-right:12px;">
                    <a href="{ci_url}" target="_blank" style="text-decoration:none;">
                      <img src="{ci_img}" alt="{esc(ci.get('title'))}" width="92" style="display:block; width:92px; height:auto; border-radius:4px; border:0;">
                    </a>
                  </td>
                  <td valign="middle">
                    <a href="{ci_url}" target="_blank" style="font-family: Georgia, serif; font-size:15px; font-weight:bold; color:{TEXT_MAIN}; text-decoration:none; line-height:1.35;">{esc(ci.get('title'))}</a>
                    <div style="font-size:11px; color:{TEXT_MUTED}; margin-top:3px;">{esc(ci.get('author', 'Bernardinai.lt'))}</div>
                  </td>
                </tr>
              </table>
            """)
        html_parts.append("            </div>")
    html_parts.append("          </td>\n        </tr>")

# 6. PARTNERIŲ VITRINA IŠ „🎁 PARTNERIŲ VITRINOS“ ĮSKIEPIO (MERCYSHOP / GYMGLISH SU STATISTIKA)
if isinstance(partner_showcase, dict) and partner_showcase.get("items"):
    ps_accent = esc(partner_showcase.get("accent") or "#a01b1b")
    ps_badge = esc(partner_showcase.get("badge") or "Partnerių vitrina")
    ps_heading = esc(partner_showcase.get("heading") or "")
    ps_sub = esc(partner_showcase.get("sub") or "")
    ps_btn_lbl = esc(partner_showcase.get("btn_label") or "Sužinoti daugiau →")
    ps_btn_url = uzkoduoti_url(partner_showcase.get("btn_url") or "https://www.bernardinai.lt/")
    ps_items = partner_showcase.get("items")[:3]

    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 10px 28px 22px 28px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#fdfbf7; border:1px solid #ead8d6; border-left:4px solid {ps_accent}; border-radius:8px;">
              <tr>
                <td style="padding: 18px 18px 14px 18px;">
                  <div style="display:inline-block; background-color:{ps_accent}; color:#ffffff; font-size:10px; font-weight:bold; text-transform:uppercase; letter-spacing:0.6px; padding:3px 9px; border-radius:4px; margin-bottom:8px;">{ps_badge}</div>
                  <div style="font-family: Georgia, serif; font-size:18px; font-weight:bold; color:{TEXT_MAIN}; line-height:1.3; margin-bottom:6px;">{ps_heading}</div>
                  {f'<div style="font-size:13px; color:#555555; line-height:1.45; margin-bottom:14px;">{ps_sub}</div>' if ps_sub else ''}
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px;">
                    <tr>
    """)

    col_w = int(100 / max(1, len(ps_items)))
    for idx_p, p_it in enumerate(ps_items):
        p_url = uzkoduoti_url(p_it.get("url") or ps_btn_url)
        p_title = esc(p_it.get("title"))
        p_price = esc(p_it.get("price"))
        p_cta = esc(p_it.get("cta") or "Peržiūrėti →")
        raw_p_img = p_it.get("image") or ""
        pad_r = "8px" if idx_p < len(ps_items) - 1 else "0"

        img_block = ""
        if raw_p_img:
            p_img_src = email_img(raw_p_img, width=220, height=160, crop=False)
            img_block = f"""
                        <a href="{p_url}" target="_blank" rel="noopener sponsored" style="text-decoration:none;">
                          <img src="{p_img_src}" alt="{p_title}" width="150" style="display:block; width:100%; max-width:150px; height:auto; margin:0 auto 8px auto; border-radius:4px; border:0;">
                        </a>
            """

        html_parts.append(f"""
                      <td class="prod-col" width="{col_w}%" valign="top" style="width:{col_w}%; padding-right:{pad_r};">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#ffffff; border:1px solid #ead8d6; border-radius:6px;">
                          <tr>
                            <td style="padding:10px;">
                              {img_block}
                              <div style="font-size:13px; font-weight:bold; line-height:1.35; margin-bottom:6px;">
                                <a href="{p_url}" target="_blank" rel="noopener sponsored" style="color:{TEXT_MAIN}; text-decoration:none;">{p_title}</a>
                              </div>
                              {f'<div style="font-size:12px; font-weight:bold; color:#1b7e2b; margin-bottom:4px;">{p_price}</div>' if p_price else ''}
                              <a href="{p_url}" target="_blank" rel="noopener sponsored" style="font-size:12px; font-weight:bold; color:{ps_accent}; text-decoration:none;">{p_cta}</a>
                            </td>
                          </tr>
                        </table>
                      </td>
        """)

    html_parts.append(f"""
                    </tr>
                  </table>
                  <div style="text-align:right;">
                    <a href="{ps_btn_url}" target="_blank" rel="noopener sponsored" style="display:inline-block; background-color:{ps_accent}; color:#ffffff; font-size:12px; font-weight:bold; text-decoration:none; padding:8px 16px; border-radius:5px;">{ps_btn_lbl}</a>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
    """)

# 7. AFIŠA – RENGINIAI IR KVIETIMAI (TIK AKTUALŪS IR DAR NESIŲSTI)
if posters:
    afisa_all_url = su_utm("https://www.bernardinai.lt/afisa/", "afisa_visi")
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 8px 28px 22px 28px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-bottom:2px solid {BRAND_ACCENT}; padding-bottom:6px; margin-bottom:14px;">
              <tr>
                <td align="left" style="font-family: Georgia, serif; font-size:19px; font-weight:bold; color:{TEXT_MAIN};">Afiša: renginiai ir kvietimai</td>
                <td align="right"><a href="{afisa_all_url}" target="_blank" style="font-size:12px; color:{BRAND_ACCENT}; font-weight:bold; text-decoration:none;">Visa afiša →</a></td>
              </tr>
            </table>
    """)
    for p_idx, po in enumerate(posters):
        p_url = su_utm(po.get("link"), f"afisa_{p_idx+1}")
        label = esc(po.get("poster_label") or "Kvietimas")
        html_parts.append(f"""
            <div style="margin-bottom:12px; padding:12px 14px; background-color:#faf6f2; border-radius:5px;">
              <span style="display:inline-block; background-color:{BRAND_ACCENT}; color:#ffffff; font-size:10px; font-weight:bold; text-transform:uppercase; padding:2px 7px; border-radius:3px; margin-bottom:5px;">{label}</span>
              <div style="font-family: Georgia, serif; font-size:15px; font-weight:bold; line-height:1.35;">
                <a href="{p_url}" target="_blank" style="color:{TEXT_MAIN}; text-decoration:none;">{esc(po.get('title'))}</a>
              </div>
            </div>
        """)
    html_parts.append("          </td>\n        </tr>")

# 8. NUOLATINIS DAUGIAKALBYSTĖS PRIMINIMAS (SKAITYMAS IR DALIJIMASIS 40+ KALBŲ)
share_base_url = hero.get("link") or "https://www.bernardinai.lt/"
kalbu_mygtukai = [
    ("en", "🇬🇧 English"),
    ("pl", "🇵🇱 Polski"),
    ("uk", "🇺🇦 Українська"),
    ("de", "🇩🇪 Deutsch"),
    ("it", "🇮🇹 Italiano"),
    ("fr", "🇫🇷 Français"),
]
kalbu_piliules_html = "".join(
    f'<a href="{su_kalba_ir_utm(share_base_url, l_code)}" target="_blank" '
    f'style="display:inline-block; background-color:#ffffff; border:1px solid #d8cfc2; '
    f'color:{TEXT_MAIN}; font-size:12px; font-weight:bold; text-decoration:none; '
    f'padding:6px 11px; border-radius:99px; margin:3px 4px 3px 0;">{l_label}</a>'
    for l_code, l_label in kalbu_mygtukai
)

html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 6px 28px 22px 28px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f9f6f1; border:1px solid #e6ddd0; border-left:4px solid {BRAND_DARK}; border-radius:8px;">
              <tr>
                <td style="padding: 16px 18px;">
                  <div style="font-size:10px; font-weight:bold; text-transform:uppercase; letter-spacing:1px; color:{BRAND_DARK}; margin-bottom:5px;">🌐 Bernardinai.lt pasauliui &bull; 40+ kalbų</div>
                  <div style="font-family: Georgia, serif; font-size:17px; font-weight:bold; color:{TEXT_MAIN}; line-height:1.3; margin-bottom:6px;">Turite bičiulių ar artimųjų užsienyje? Dalinkitės kitomis kalbomis</div>
                  <div style="font-size:13px; color:#555555; line-height:1.5; margin-bottom:10px;">
                    Kiekvieną „Bernardinai.lt“ tekstą svetainėje galima skaityti su automatiniu vertimu (viršuje paspaudus mygtuką <strong>🌐 LT</strong>). Atidarykite ir persiųskite šiandienos pagrindinę temą norima kalba:
                  </div>
                  <div style="line-height:1.8;">
                    {kalbu_piliules_html}
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
""")

# 9. PARAMOS BLOKAS IR REKVIZITAI (SU TIESIOGINIAIS STRIPE 5€ / 10€ / 25€ MYGTUKAIS)
parama_url = su_utm("https://www.bernardinai.lt/parama/", "footer_parama")
stripe_5 = "https://buy.stripe.com/eVqbJ22Me4Qh4Xd2V6aIM06"
stripe_10 = "https://buy.stripe.com/28E7sM5YqfuVblBeDOaIM07"
stripe_25 = "https://buy.stripe.com/6oU6oI2Me2I9ahx67iaIM08"

html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 26px 28px; background-color:{BRAND_DARK}; color:#ffffff; text-align:center;">
            <div style="font-family: Georgia, serif; font-size:20px; font-weight:bold; margin-bottom:8px;">Palaikykite nepriklausomą „Bernardinai.lt“ žurnalistiką</div>
            <p style="font-size:13px; line-height:1.55; color:#f2dedd; margin:0 0 16px 0;">
              „Bernardinai.lt“ neturi politinių ar verslo šeimininkų ir gyvuoja tik skaitytojų paramos dėka. Pasirinkite paramos sumą arba visus būdus:
            </p>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto 14px auto;">
              <tr>
                <td style="padding:0 5px;">
                  <a href="{stripe_5}" target="_blank" style="display:inline-block; background-color:rgba(255,255,255,0.14); border:1px solid rgba(255,255,255,0.45); color:#ffffff; font-size:14px; font-weight:bold; text-decoration:none; padding:8px 16px; border-radius:6px;">☕ 5 €</a>
                </td>
                <td style="padding:0 5px;">
                  <a href="{stripe_10}" target="_blank" style="display:inline-block; background-color:{BRAND_ACCENT}; border:1px solid #ffffff; color:#ffffff; font-size:14px; font-weight:bold; text-decoration:none; padding:8px 18px; border-radius:6px;">❤️ 10 €</a>
                </td>
                <td style="padding:0 5px;">
                  <a href="{stripe_25}" target="_blank" style="display:inline-block; background-color:rgba(255,255,255,0.14); border:1px solid rgba(255,255,255,0.45); color:#ffffff; font-size:14px; font-weight:bold; text-decoration:none; padding:8px 16px; border-radius:6px;">🌟 25 €</a>
                </td>
              </tr>
            </table>
            <div style="margin-bottom:18px;">
              <a href="{parama_url}" target="_blank" style="display:inline-block; background-color:#ffffff; color:{BRAND_DARK}; font-size:13px; font-weight:bold; text-decoration:none; padding:10px 22px; border-radius:5px;">Visi paramos būdai (banku, kortele, Paysera) →</a>
            </div>
            <div style="font-size:12px; line-height:1.6; color:#ebd4d2; border-top:1px solid rgba(255,255,255,0.2); padding-top:14px;">
              <strong>VŠĮ BERNARDINAI.LT</strong> &nbsp;|&nbsp; Įmonės kodas: 300671187<br>
              Sąskaitos Nr.: <strong>LT06 7044 0600 0598 4890</strong> (AB SEB bankas, kodas 70440, SWIFT: CBVILT2X)
            </div>
          </td>
        </tr>

        <!-- PORAŠTĖ IR PRENUMERATOS VALDYMAS -->
        <tr>
          <td class="content-pad" style="padding: 20px 28px; background-color:#ffffff; text-align:center; font-size:12px; line-height:1.6; color:#888888;">
            Interneto dienraštis „Bernardinai.lt“ &nbsp;|&nbsp; Maironio g. 10, LT-01124 Vilnius &nbsp;|&nbsp; +370 673 45416<br>
            El. paštas: <a href="mailto:redakcija@bernardinai.lt" style="color:#666666;">redakcija@bernardinai.lt</a>, <a href="mailto:reklama@bernardinai.lt" style="color:#666666;">reklama@bernardinai.lt</a><br><br>
            Jūs gavote šį laišką, nes užsiprenumeravote „Bernardinai.lt“ dienos naujienlaiškį.<br>
            <a href="{{$url}}" style="color:#666666; text-decoration:underline;">Peržiūrėti naršyklėje</a> &nbsp;|&nbsp;
            <a href="{{$unsubscribe}}" style="color:#666666; text-decoration:underline;">Atsisakyti naujienlaiškio</a>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
""")

email_html = "".join(html_parts)

os.makedirs("archyvas", exist_ok=True)
local_preview_path = f"archyvas/kasdienis_naujienlaiskis_{today_str}.html"
with open(local_preview_path, "w", encoding="utf-8") as f_out:
    f_out.write(email_html)
print(f">>> Sugeneruotas HTML failas: {local_preview_path}")

# =========================================================================
# MAILERLITE CLASSIC API V2: KAMPANIJOS SUKŪRIMAS IR SIUNTIMAS / JUODRAŠTIS
# =========================================================================
if nl_rezimas in ("siusti", "juodrastis"):
    subject_prefix = "[BANDOMASIS] " if nl_rezimas == "juodrastis" else ""
    bazine_tema = suformuoti_laisko_tema(
        main_posts,
        editorials,
        categories,
        f"{menesiai[now_lt.month - 1]} {now_lt.day} d.",
    )
    subject_line = f"{subject_prefix}{bazine_tema}"
    campaign_internal_name = f"{subject_prefix}Kasdienis naujienlaiškis ({today_str})"
    print(f">>> Suformuota laiško tema: {subject_line}")
    print(f">>> Vidinis MailerLite pavadinimas: {campaign_internal_name}")

    payload_campaign = {
        "name": campaign_internal_name,
        "type": "regular",
        "groups": [group_id],
        "subject": subject_line,
        "from": "naujienlaiskis@bernardinai.lt",
        "from_name": "Bernardinai.lt",
        "language": "lt",
        "google_analytics": f"dienos-temos-{today_str}",
    }

    req_campaign = urllib.request.Request(
        "https://api.mailerlite.com/api/v2/campaigns",
        data=json.dumps(payload_campaign).encode("utf-8"),
        headers={
            "X-MailerLite-ApiKey": api_key,
            "Content-Type": "application/json",
            "User-Agent": INTERNAL_USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(req_campaign, timeout=30) as response:
            campaign_data = json.loads(response.read().decode("utf-8"))
            campaign_id = campaign_data.get("id")
            if not campaign_id:
                kritine_klaida("MailerLite negrąžino kampanijos ID!")
            print(f">>> MailerLite kampanija sukurta! ID: {campaign_id}")

        plain_lines = [
            f"Bernardinai.lt – Dienos temos ({data_trumpiems})",
            "",
            f"PAGRINDINĖ TEMA: {hero.get('title')} ({hero.get('link')})",
            "",
        ]
        for s in secondary_main:
            plain_lines.append(f"- {s.get('title')}: {s.get('link')}")
        plain_lines.extend(
            [
                "",
                f"Skaitykite ir dalinkitės „Bernardinai.lt“ 40+ kalbų (EN/PL/UK/DE/IT): {su_kalba_ir_utm(share_base_url, 'en')}",
                "",
                "Peržiūrėti naršyklėje: {$url}",
                "Atsisakyti naujienlaiškio: {$unsubscribe}",
            ]
        )

        payload_content = {
            "html": email_html,
            "plain": "\n".join(plain_lines),
        }

        req_content = urllib.request.Request(
            f"https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/content",
            data=json.dumps(payload_content).encode("utf-8"),
            headers={
                "X-MailerLite-ApiKey": api_key,
                "Content-Type": "application/json",
                "User-Agent": INTERNAL_USER_AGENT,
            },
            method="PUT",
        )
        with urllib.request.urlopen(req_content, timeout=30):
            print(">>> MailerLite laiško HTML turinys įkeltas sėkmingai!")

        if nl_rezimas == "siusti":
            req_send = urllib.request.Request(
                f"https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/actions/send",
                data=json.dumps({}).encode("utf-8"),
                headers={
                    "X-MailerLite-ApiKey": api_key,
                    "Content-Type": "application/json",
                    "User-Agent": INTERNAL_USER_AGENT,
                },
                method="POST",
            )
            with urllib.request.urlopen(req_send, timeout=30):
                print(
                    ">>> Kasdienis naujienlaiškis sėkmingai perkeltas į OUTBOX"
                    " ir pradėtas siųsti prenumeratoriams!"
                )
            # Pažymime išsiųstus straipsnius ir citatą WordPress duomenų bazėje
            q_hash = quote.get("hash", "") if isinstance(quote, dict) else ""
            pazymeti_issiustus_straipsnius_wp(issue_post_ids, q_hash)
        else:
            print(
                ">>> SAUGUS REŽIMAS: Laiškas išsaugotas jūsų MailerLite"
                " paskyroje kaip JUODRAŠTIS (Campaigns -> Drafts)."
            )

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        kritine_klaida(f"Klaida MailerLite API (kodas {e.code}): {err_body}")
    except SystemExit:
        raise
    except Exception as e:
        kritine_klaida(f"Klaida bendraujant su MailerLite: {e}")
else:
    print(">>> MailerLite siuntimas išjungtas ('nesiusti').")
