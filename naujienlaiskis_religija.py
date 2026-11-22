import argparse
import base64
import datetime
from datetime import timedelta
import io
import json
import logging
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import feedparser
from weasyprint import HTML

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# =========================================================================
# KONFIGŪRACIJA IR SAUGOS KONSTANTOS
# =========================================================================
LT_TZ = ZoneInfo("Europe/Vilnius")

CF_SECRET_KEY = os.environ.get(
    "CF_AUTOMATION_KEY", "BernardinuNaujienlaiskisLabaiSlapt@00"
).strip()
INTERNAL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    " Bernardinai-Naujienlaiskis-Bot Bernardinai-Internal-Agent-x9K2"
)

feedparser.USER_AGENT = INTERNAL_USER_AGENT

MIN_PAGRINDINIAI_STR = int(os.environ.get("MIN_PAGRINDINIAI_STR", "1"))
MIN_VISO_STR = int(os.environ.get("MIN_VISO_STR", "3"))
MIN_TEKSTO_ILGIS = int(os.environ.get("MIN_TEKSTO_ILGIS", "200"))


def kritine_klaida(pranesimas):
    """Nedelsiant sustabdo procesą, kad nebūtų publikuotas ar išsiųstas nepilnas leidinys."""
    print(f"\n>>> KRITINĖ APSAUGOS KLAIDA: {pranesimas}")
    print(
        ">>> Publikavimas, FTP kėlimas ir naujienlaiškio siuntimas"
        " SUSTABDYTI."
    )
    sys.exit(1)


# =========================================================================
# PALEIDIMO PARAMETRŲ NUSKAITYMAS (ENV ARBA KOMANDINĖ EILUTĖ)
# =========================================================================
parser = argparse.ArgumentParser(
    description="Bernardinai.lt Religijos savaitraščio generatorius"
)
parser.add_argument(
    "--rezimas",
    default="",
    help="Paleidimo režimas: bandomasis | tikras | tik_atnaujinti_pdf",
)
parser.add_argument(
    "--numeris",
    default="",
    help="Pasirinktinis leidinio numeris, pvz.: 47 arba 2026/47",
)
parser.add_argument(
    "--data",
    default="",
    help="Pasirinktinė leidinio data YYYY-MM-DD, pvz.: 2026-11-22",
)
parser.add_argument(
    "--naujienlaiskis",
    default="",
    help="Naujienlaiškio veiksmas: auto | siusti | juodrastis | nesiusti",
)
parser.add_argument(
    "--wp",
    default="",
    help="WordPress įrašo veiksmas: auto | publish | draft | ne",
)
args, _ = parser.parse_known_args()

event_name = os.environ.get("EVENT_NAME", "").strip()
force_real_legacy = (
    os.environ.get("TIKRAS_LEIDINYS", "false").strip().lower() == "true"
)

raw_rezimas = (
    args.rezimas or os.environ.get("PALEIDIMO_REZIMAS", "")
).strip().lower()

if not raw_rezimas:
    if event_name == "schedule" or force_real_legacy:
        paleidimo_rezimas = "tikras"
    else:
        paleidimo_rezimas = "bandomasis"
else:
    rezimu_map = {
        "bandomasis": "bandomasis",
        "test": "bandomasis",
        "draft": "bandomasis",
        "tikras": "tikras",
        "iprastas_tikras": "tikras",
        "real": "tikras",
        "publish": "tikras",
        "tik_atnaujinti_pdf": "tik_atnaujinti_pdf",
        "atnaujinti_pdf": "tik_atnaujinti_pdf",
        "pdf_only": "tik_atnaujinti_pdf",
    }
    if raw_rezimas not in rezimu_map:
        kritine_klaida(
            f"Nežinomas PALEIDIMO_REZIMAS='{raw_rezimas}'. Galimos reikšmės:"
            " bandomasis, tikras, tik_atnaujinti_pdf."
        )
    paleidimo_rezimas = rezimu_map[raw_rezimas]

is_real_run = paleidimo_rezimas in ("tikras", "tik_atnaujinti_pdf")

# Automatinio tvarkaraščio laiko patikra (tik schedule paleidimui)
if event_name == "schedule":
    lt_time = datetime.datetime.now(LT_TZ)
    if not (6 <= lt_time.hour <= 10):
        print(
            f"Dabar Lietuvoje yra {lt_time.hour} val. Agentas ilsisi, nes"
            " siuntimo laikas yra tarp 06:00 ir 10:00 val."
        )
        sys.exit(0)

# Naujienlaiškio siuntimo režimas
raw_nl = (
    args.naujienlaiskis or os.environ.get("SIUSTI_NAUJIENLAISKI", "auto")
).strip().lower()

if raw_nl in ("", "auto"):
    if paleidimo_rezimas == "tikras":
        nl_rezimas = "siusti"
    elif paleidimo_rezimas == "bandomasis":
        nl_rezimas = "juodrastis"
    else:  # tik_atnaujinti_pdf
        nl_rezimas = "nesiusti"
elif raw_nl in ("siusti", "true", "taip", "1", "yes", "send"):
    nl_rezimas = "siusti"
elif raw_nl in ("juodrastis", "draft"):
    nl_rezimas = "juodrastis"
elif raw_nl in ("nesiusti", "false", "ne", "0", "no", "none"):
    nl_rezimas = "nesiusti"
else:
    kritine_klaida(
        f"Nežinoma SIUSTI_NAUJIENLAISKI reikšmė: '{raw_nl}'. Galimos:"
        " auto, siusti, juodrastis, nesiusti."
    )

if nl_rezimas == "siusti" and paleidimo_rezimas == "bandomasis":
    kritine_klaida(
        "Bandomuoju režimu (kai PDF nekeliamas į FTP serverį) draudžiama"
        " išsiųsti tikrą naujienlaiškį prenumeratoriams!"
    )

# WordPress publikavimo režimas
raw_wp = (args.wp or os.environ.get("PUBLIKUOTI_WP", "auto")).strip().lower()
if raw_wp in ("", "auto"):
    if paleidimo_rezimas == "tikras":
        wp_rezimas = "publish"
    elif paleidimo_rezimas == "bandomasis":
        wp_rezimas = "draft"
    else:  # tik_atnaujinti_pdf
        wp_rezimas = "ne"
elif raw_wp in ("publish", "true", "taip", "1"):
    wp_rezimas = "publish"
elif raw_wp in ("draft", "juodrastis"):
    wp_rezimas = "draft"
elif raw_wp in ("ne", "false", "0", "no", "none"):
    wp_rezimas = "ne"
else:
    kritine_klaida(
        f"Nežinoma PUBLIKUOTI_WP reikšmė: '{raw_wp}'. Galimos: auto, publish,"
        " draft, ne."
    )

# =========================================================================
# LEIDINIO DATOS IR NUMERIO NUSTATYMAS
# =========================================================================
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

custom_date_raw = (
    args.data or os.environ.get("LEIDINIO_DATA_CUSTOM", "")
).strip()
custom_num_raw = (
    args.numeris or os.environ.get("LEIDINIO_NUMERIS_CUSTOM", "")
).strip()

now_lt = datetime.datetime.now(LT_TZ).replace(tzinfo=None)

if custom_date_raw:
    try:
        parsed_d = datetime.date.fromisoformat(custom_date_raw)
        today = datetime.datetime(
            parsed_d.year, parsed_d.month, parsed_d.day, 23, 59, 59
        )
    except ValueError:
        kritine_klaida(
            f"Neteisingas LEIDINIO_DATA_CUSTOM formatas '{custom_date_raw}'."
            " Naudokite YYYY-MM-DD (pvz., 2026-11-22)."
        )
else:
    today = now_lt

today_str = today.strftime("%Y-%m-%d")
start_date_obj = today.date() - timedelta(days=7)
one_week_ago = datetime.datetime(
    start_date_obj.year, start_date_obj.month, start_date_obj.day, 0, 0, 0
)

leidinio_data = f"{today.year} m. {menesiai[today.month - 1]} {today.day} d."
savaites_laikotarpis = (
    f"{one_week_ago.year} m. {menesiai[one_week_ago.month - 1]}"
    f" {one_week_ago.day} d. – {today.year} m. {menesiai[today.month - 1]}"
    f" {today.day} d."
)

tracker_file = "leidinio_numeris_religija.txt"
current_year = today.year
numeris = 1
saved_year = 0
saved_num = 0
last_run_date = ""

if os.path.exists(tracker_file):
    try:
        with open(tracker_file, "r", encoding="utf-8") as f:
            t_parts = f.read().strip().split("/")
            saved_year = int(t_parts[0])
            saved_num = int(t_parts[1])
            last_run_date = t_parts[2] if len(t_parts) >= 3 else ""
    except Exception:
        pass

if custom_num_raw:
    m_num = re.match(r"^(?:(\d{4})\s*/\s*)?(\d+)$", custom_num_raw)
    if not m_num:
        kritine_klaida(
            f"Neteisingas LEIDINIO_NUMERIS_CUSTOM='{custom_num_raw}'."
            " Įrašykite skaičių (pvz., 47) arba metus/numerį (pvz., 2026/47)."
        )
    if m_num.group(1):
        current_year = int(m_num.group(1))
    numeris = int(m_num.group(2))
    leidinio_numeris = f"{current_year}/{numeris}"
elif paleidimo_rezimas == "tikras":
    if saved_year == current_year:
        if last_run_date == today_str:
            if event_name == "schedule":
                print(
                    ">>> Šios dienos numeris jau buvo išleistas!"
                    " Stabdome automatinį procesą, kad išvengtume dublikatų."
                )
                sys.exit(0)
            else:
                kritine_klaida(
                    f"Šios dienos ({today_str}) numeris jau buvo išleistas"
                    f" ({saved_year}/{saved_num}). Jei norite tik pakeisti PDF"
                    " failą, rinkitės PALEIDIMO_REZIMAS='tik_atnaujinti_pdf',"
                    " arba nurodykite LEIDINIO_NUMERIS_CUSTOM."
                )
        numeris = saved_num + 1
    else:
        numeris = 1
    leidinio_numeris = f"{current_year}/{numeris}"
elif paleidimo_rezimas == "tik_atnaujinti_pdf":
    if saved_year == current_year and saved_num > 0:
        numeris = saved_num
    else:
        numeris = 1
    leidinio_numeris = f"{current_year}/{numeris}"
else:
    leidinio_numeris = "Bandomasis"

print("=================================================================")
print(f"LEIDINYS:               Religijos naujienų ir tikėjimo savaitraštis")
print(f"PALEIDIMO REŽIMAS:      {paleidimo_rezimas}")
print(f"LEIDINIO NUMERIS:       {leidinio_numeris}")
print(f"LEIDINIO DATA:          {leidinio_data} ({today_str})")
print(f"STRAIPSNIŲ INTERVALAS:  {savaites_laikotarpis}")
print(f"WORDPRESS PUBLIKAVIMAS: {wp_rezimas}")
print(f"NAUJIENLAIŠKIS:         {nl_rezimas}")
print("=================================================================")

# =========================================================================
# PRIVALOMŲ PRISIJUNGIMŲ PATIKRA PRIEŠ PRADEDANT DARBĄ
# =========================================================================
api_key = os.environ.get("MAILERLITE_API_KEY", "").strip()
ftp_server = os.environ.get("FTP_SERVER", "").strip()
ftp_user = os.environ.get("FTP_USERNAME", "").strip()
ftp_pass = os.environ.get("FTP_PASSWORD", "").strip()
wp_user = os.environ.get("WP_USERNAME", "").strip()
wp_pass = os.environ.get("WP_APP_PASSWORD", "").strip()

if is_real_run and not (ftp_server and ftp_user and ftp_pass):
    kritine_klaida(
        "Tikram leidimui arba PDF atnaujinimui privalomi FTP_SERVER,"
        " FTP_USERNAME ir FTP_PASSWORD duomenys!"
    )

if nl_rezimas in ("siusti", "juodrastis") and not api_key:
    kritine_klaida(
        f"Pasirinktas naujienlaiškio režimas '{nl_rezimas}', bet nerastas"
        " MAILERLITE_API_KEY!"
    )

if wp_rezimas in ("publish", "draft") and not (wp_user and wp_pass):
    if wp_rezimas == "publish":
        kritine_klaida(
            "Pasirinktas WordPress publikavimas, bet nerasti WP_USERNAME arba"
            " WP_APP_PASSWORD!"
        )
    else:
        print(
            ">>> ĮSPĖJIMAS: WP_USERNAME/WP_APP_PASSWORD nerasti, bandomasis WP"
            " juodraštis nebus kuriamas."
        )
        wp_rezimas = "ne"

wp_headers = {
    "User-Agent": INTERNAL_USER_AGENT,
    "X-Bnd-Automate": CF_SECRET_KEY,
    "Referer": "https://www.bernardinai.lt/",
}
if wp_user and wp_pass:
    auth_str = f"{wp_user}:{wp_pass.replace(' ', '')}"
    basic_val = (
        f"Basic {base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')}"
    )
    wp_headers.update(
        {
            "Authorization": basic_val,
            "X-HTTP-Authorization": basic_val,
            "REDIRECT_HTTP_AUTHORIZATION": basic_val,
        }
    )

# =========================================================================
# PAGALBINĖS FUNKCIJOS IR SAUGUS NUOTRAUKŲ PARSIUNTIMAS / PATIKRA
# =========================================================================
def uzkoduoti_url_saugiai(url):
    """Saugiai užkoduoja lietuviškas raides, tarpus ir spec. simbolius URL adrese."""
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url.strip())
    clean_path = urllib.parse.quote(
        urllib.parse.unquote(parts.path), safe="/:@!$&'()*+,;=-._~"
    )
    clean_query = urllib.parse.quote(
        urllib.parse.unquote(parts.query), safe="=&:@!$'()*+,;-._~%"
    )
    return urllib.parse.urlunsplit(
        (parts.scheme or "https", parts.netloc, clean_path, clean_query, "")
    )


try:
    from weasyprint.urls import URLFetcher

    weasyprint_url_fetcher = URLFetcher(
        headers={
            "User-Agent": INTERNAL_USER_AGENT,
            "X-Bnd-Automate": CF_SECRET_KEY,
            "Referer": "https://www.bernardinai.lt/",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }
    )
except Exception:
    from weasyprint import default_url_fetcher

    def weasyprint_url_fetcher(url, timeout=20, ssl_context=None):
        if url.startswith("http"):
            req = urllib.request.Request(
                uzkoduoti_url_saugiai(url),
                headers={
                    "User-Agent": INTERNAL_USER_AGENT,
                    "X-Bnd-Automate": CF_SECRET_KEY,
                    "Referer": "https://www.bernardinai.lt/",
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(
                req, timeout=timeout, context=ssl_context
            ) as resp:
                return {
                    "string": resp.read(),
                    "mime_type": resp.headers.get_content_type(),
                    "encoding": resp.headers.get_content_charset(),
                    "redirected_url": resp.geturl(),
                }
        return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)


def gauti_linksni(skaicius):
    paskutiniai_du = skaicius % 100
    paskutinis = skaicius % 10
    if 11 <= paskutiniai_du <= 19 or paskutinis == 0:
        return "prenumeratorių"
    elif paskutinis == 1:
        return "prenumeratoriui"
    else:
        return "prenumeratoriams"


def gauti_paskutines_kampanijos_gavejus(ml_key):
    if not ml_key:
        return None
    try:
        url = "https://api.mailerlite.com/api/v2/campaigns/sent"
        req = urllib.request.Request(
            url,
            headers={
                "X-MailerLite-ApiKey": ml_key,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            kampanijos = json.loads(response.read().decode("utf-8"))
            if kampanijos and len(kampanijos) > 0:
                paskutine = kampanijos[0]
                return paskutine.get(
                    "total_recipients", paskutine.get("recipients_count", 0)
                )
    except Exception as e:
        print(f"Nepavyko gauti praėjusio numerio gavėjų skaičiaus: {e}")
    return None


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

logo_src = ""
logo_failas = "logo.png"
if os.path.exists(logo_failas):
    with open(logo_failas, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        logo_src = f"data:image/png;base64,{encoded_string}"
else:
    kritine_klaida(f"Nerastas logotipo failas '{logo_failas}'!")


def isvalyti_img_url(url):
    if not url:
        return ""
    url = url.replace("&#038;", "&").replace("&amp;", "&").strip()
    if "images.weserv.nl" in url and "url=" in url:
        match = re.search(r"url=([^&]+)", url)
        if match:
            url = urllib.parse.unquote(match.group(1))
    if url and not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return uzkoduoti_url_saugiai(url)


def sukurti_email_img_url(clean_direct_url):
    if not clean_direct_url:
        return ""
    if ".webp" in clean_direct_url.lower():
        be_schemos = re.sub(r"^https?://", "", clean_direct_url, flags=re.I)
        return (
            "https://images.weserv.nl/?url="
            f"{urllib.parse.quote(be_schemos, safe='')}&output=jpg&w=800&q=85"
        )
    return clean_direct_url


def ar_tikri_paveikslelio_baitai(data):
    if not data or len(data) < 400:
        return False
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    return False


nuotrauku_podelis = {}


def parsiusti_ir_patikrinti_nuotrauka(raw_url, kontekstas=""):
    """
    Parsiunčia nuotrauką, patikrina jos vientisumą ir paruošia Base64 URI PDF generavimui.
    Jei nuotraukos parsiųsti nepavyksta – nedelsiant stabdo visą skriptą!
    """
    clean_url = isvalyti_img_url(raw_url)
    if not clean_url:
        kritine_klaida(f"Tuščias nuotraukos adresas ({kontekstas})!")

    if clean_url in nuotrauku_podelis:
        return nuotrauku_podelis[clean_url]

    be_schemos = re.sub(r"^https?://", "", clean_url, flags=re.I)
    weserv_fallback = (
        "https://images.weserv.nl/?url="
        f"{urllib.parse.quote(be_schemos, safe='')}&output=jpg&w=1200&q=88"
    )

    kandidatai = [clean_url, weserv_fallback]
    if "bernardinai.lt" in clean_url and "?" in clean_url:
        kandidatai.insert(1, clean_url.split("?")[0])

    parsiusti_baitai = None
    paskutine_klaida = ""

    for bandymo_url in kandidatai:
        for _ in range(2):
            try:
                headers = {
                    "User-Agent": INTERNAL_USER_AGENT,
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": "https://www.bernardinai.lt/",
                }
                if "bernardinai.lt" in bandymo_url:
                    headers["X-Bnd-Automate"] = CF_SECRET_KEY

                req = urllib.request.Request(bandymo_url, headers=headers)
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = resp.read()
                    if ar_tikri_paveikslelio_baitai(data):
                        parsiusti_baitai = data
                        break
                    else:
                        paskutine_klaida = (
                            f"Gautas ne paveikslėlis ({len(data)} B,"
                            f" Content-Type: {resp.headers.get_content_type()})"
                        )
            except Exception as e:
                paskutine_klaida = str(e)
                time.sleep(1.5)
        if parsiusti_baitai:
            break

    if not parsiusti_baitai:
        kritine_klaida(
            f"Nepavyko parsiųsti nuotraukos [{kontekstas}] iš {clean_url}."
            f" Priežastis: {paskutine_klaida}"
        )

    galutiniai_baitai = parsiusti_baitai
    mime_type = "image/jpeg"

    if HAS_PIL:
        try:
            with Image.open(io.BytesIO(parsiusti_baitai)) as im:
                im.load()
                if im.width > 1600:
                    santykis = 1600.0 / float(im.width)
                    naujas_aukstis = max(1, int(im.height * santykis))
                    im = im.resize((1600, naujas_aukstis), Image.LANCZOS)

                out_buf = io.BytesIO()
                if im.mode in ("RGBA", "LA") or (
                    im.mode == "P" and "transparency" in im.info
                ):
                    im.save(out_buf, format="PNG", optimize=True)
                    mime_type = "image/png"
                else:
                    im.convert("RGB").save(
                        out_buf, format="JPEG", quality=88, optimize=True
                    )
                    mime_type = "image/jpeg"
                galutiniai_baitai = out_buf.getvalue()
        except Exception as e:
            kritine_klaida(
                f"Sugadintas nuotraukos failas [{kontekstas}] ({clean_url}): {e}"
            )
    else:
        if parsiusti_baitai[:8] == b"\x89PNG\r\n\x1a\n":
            mime_type = "image/png"
        elif (
            parsiusti_baitai[:4] == b"RIFF"
            and parsiusti_baitai[8:12] == b"WEBP"
        ):
            mime_type = "image/webp"

    b64_str = base64.b64encode(galutiniai_baitai).decode("ascii")
    rezultatas = {
        "data_uri": f"data:{mime_type};base64,{b64_str}",
        "email_url": sukurti_email_img_url(clean_url),
        "clean_url": clean_url,
        "bytes": galutiniai_baitai,
        "mime": mime_type,
    }
    nuotrauku_podelis[clean_url] = rezultatas
    return rezultatas


def rasti_nuotrauka_per_wp_api(post_link):
    """Jei RSS įraše nebuvo nuotraukos, bando ją surasti tiesiai per WP REST API pagal slug."""
    slug = post_link.rstrip("/").split("/")[-1]
    if not slug:
        return ""
    api_u = (
        "https://www.bernardinai.lt/wp-json/wp/v2/posts"
        f"?slug={urllib.parse.quote(slug)}&_embed=1"
    )
    try:
        req = urllib.request.Request(api_u, headers=wp_headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            arr = json.loads(r.read().decode("utf-8"))
            if arr and isinstance(arr, list):
                p = arr[0]
                img = isvalyti_img_url(p.get("featured_image_src", ""))
                if not img:
                    emb = p.get("_embedded", {})
                    media = emb.get("wp:featuredmedia", [])
                    if media and isinstance(media[0], dict):
                        img = isvalyti_img_url(media[0].get("source_url", ""))
                return img
    except Exception:
        pass
    return ""


try:
    from reklamos import gauti_reklamos_bloka
except Exception as e:
    print(
        f"Nepavyko užkrauti reklamos modulio ({e}). Naudojamas standartinis"
        " blokas."
    )

    def gauti_reklamos_bloka(leidinys, vieta_idx=0, formatas="pdf"):
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
                <div style="font-size: 13px; color: #666;">Kreipkitės: <a href="mailto:reklama@bernardinai.lt" style="color: #2b5c8f; font-weight: bold; text-decoration: none;">reklama@bernardinai.lt</a></div>
            </div>
            """


# =========================================================================
# STRAIPSNIŲ NUSKAITYMAS SU PILNUMO KONTROLE
# =========================================================================
matyti_url = set()
pagrindiniai_straipsniai = []
kiti_straipsniai = []


def nuskaityti_rss_srauta(rss_url):
    """
    Nuskaito RSS srautą, išvalo XML valdymo šiukšles ir patikrina, ar XML nėra nukirptas.
    Grąžina: (parsed_feed, status_code, klaidos_tekstas)
    """
    try:
        req = urllib.request.Request(
            rss_url,
            headers={
                "User-Agent": INTERNAL_USER_AGENT,
                "X-Bnd-Automate": CF_SECRET_KEY,
                "Referer": "https://www.bernardinai.lt/",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw_xml = resp.read()
            clean_xml = re.sub(
                rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", b"", raw_xml
            )
            if b"</rss>" not in clean_xml.lower():
                return (
                    None,
                    500,
                    f"Gautas nepilnas (nukirptas) RSS XML iš {rss_url}!",
                )
            parsed = feedparser.parse(clean_xml)
            if getattr(parsed, "bozo", False) and not parsed.entries:
                return (
                    None,
                    500,
                    f"Sugadinta RSS XML struktūra ({rss_url}):"
                    f" {getattr(parsed, 'bozo_exception', '')}",
                )
            print(f"RSS {rss_url} -> rasta įrašų: {len(parsed.entries)}")
            return parsed, 200, ""
    except urllib.error.HTTPError as e:
        print(f"HTTP klaida {e.code} nuskaitant {rss_url}: {e.reason}")
        return None, e.code, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        print(f"Tinklo klaida nuskaitant {rss_url}: {e}")
        return None, 0, str(e)


def konvertuoti_rss_data_lt(entry, kontekstas=""):
    if not getattr(entry, "published_parsed", None):
        kritine_klaida(f"Straipsnis neturi publikavimo datos ({kontekstas})!")
    pub_utc = datetime.datetime(
        *entry.published_parsed[:6], tzinfo=datetime.timezone.utc
    )
    return pub_utc.astimezone(LT_TZ).replace(tzinfo=None)


def apdoroti_straipsni(entry, is_main=True):
    link = getattr(entry, "link", "").strip()
    if not link or link == "#":
        kritine_klaida("Rastas straipsnis be nuorodos (link)!")

    if link in matyti_url:
        return None

    raw_title = (
        getattr(entry, "title", "").replace("\n", " ").replace("\r", "").strip()
    )
    if not raw_title:
        kritine_klaida(f"Rastas straipsnis be pavadinimo ({link})!")

    title_lower = raw_title.lower()
    if (
        "religijos naujienų" in title_lower
        or "tikėjimo savaitraštis" in title_lower
        or "kultūros savaitraštis" in title_lower
        or "savaitraštis nr." in title_lower
    ):
        print(f"Praleidžiamas savaitraščio įrašas: {raw_title}")
        return None

    pub_date_obj = konvertuoti_rss_data_lt(entry, raw_title)

    if pub_date_obj > today:
        return None
    if pub_date_obj < one_week_ago:
        return "SENESNIS"

    data_lt = (
        f"{pub_date_obj.year} m. {menesiai[pub_date_obj.month - 1]}"
        f" {pub_date_obj.day} d."
    )

    saltinis = "Bernardinai.lt"
    if not is_main:
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            saltinis = entry.source.title

    autorius = ""
    if hasattr(entry, "authors") and entry.authors:
        names = [
            a.get("name", "").strip()
            for a in entry.authors
            if isinstance(a, dict) and a.get("name")
        ]
        names = [
            n
            for n in names
            if n.lower() not in ["admin", "bernardinai.lt", "redakcija"]
        ]
        if len(names) == 1:
            autorius = names[0]
        elif len(names) == 2:
            autorius = f"{names[0]} ir {names[1]}"
        elif len(names) > 2:
            autorius = ", ".join(names[:-1]) + f" ir {names[-1]}"

    if not autorius:
        raw_author = (
            getattr(entry, "author", "")
            or getattr(entry, "creator", "")
            or getattr(entry, "dc_creator", "")
            or ""
        ).strip()
        if raw_author.lower() not in ["admin", "bernardinai.lt", "redakcija"]:
            parts = [p.strip() for p in raw_author.split(",") if p.strip()]
            if len(parts) == 1:
                autorius = parts[0]
            elif len(parts) == 2:
                autorius = f"{parts[0]} ir {parts[1]}"
            elif len(parts) > 2:
                autorius = ", ".join(parts[:-1]) + f" ir {parts[-1]}"
            else:
                autorius = raw_author

    if not autorius:
        autorius = "Bernardinai.lt"

    aprasymas = getattr(entry, "description", "")
    izanga_clean = re.sub("<[^<]+>", "", aprasymas).strip()
    izanga_clean = (
        izanga_clean[:250] + "..."
        if len(izanga_clean) > 250
        else izanga_clean
    )

    tituline_nuotrauka = ""
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if media.get("url"):
                tituline_nuotrauka = isvalyti_img_url(media["url"])
                break

    if (
        not tituline_nuotrauka
        and hasattr(entry, "enclosures")
        and entry.enclosures
    ):
        for enc in entry.enclosures:
            enc_url = enc.get("href") or enc.get("url") or ""
            if enc.get("type", "").startswith("image/") or enc_url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp")
            ):
                tituline_nuotrauka = isvalyti_img_url(enc_url)
                break

    if not tituline_nuotrauka:
        paveikslelis = re.search(r'<img[^>]+src="([^">]+)"', aprasymas)
        if paveikslelis:
            tituline_nuotrauka = isvalyti_img_url(paveikslelis.group(1))

    if (
        not tituline_nuotrauka
        and hasattr(entry, "content")
        and len(entry.content) > 0
    ):
        paveikslelis_tekste = re.search(
            r'<img[^>]+src="([^">]+)"', entry.content[0].value
        )
        if paveikslelis_tekste:
            tituline_nuotrauka = isvalyti_img_url(
                paveikslelis_tekste.group(1)
            )

    if not (
        hasattr(entry, "content")
        and len(entry.content) > 0
        and entry.content[0].value
    ):
        kritine_klaida(
            f"Straipsnyje „{raw_title}“ trūksta pilno teksto (content:encoded)!"
        )

    pilnas_tekstas = entry.content[0].value
    grynasis_ilgis = len(re.sub(r"<[^>]+>", "", pilnas_tekstas).strip())
    if grynasis_ilgis < MIN_TEKSTO_ILGIS:
        kritine_klaida(
            f"Straipsnio „{raw_title}“ tekstas neįprastai trumpas arba"
            f" nukirptas ({grynasis_ilgis} simb.)!"
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
        "title": raw_title,
        "author": autorius,
        "source": saltinis,
        "date": data_lt,
        "pub_date_obj": pub_date_obj,
        "image": tituline_nuotrauka,
        "excerpt": izanga_clean,
        "content": pilnas_tekstas,
        "link": link,
    }


def surinkti_srauto_straipsnius(feed_slug, is_main, tikslinis_sarasas):
    puslapio_pirmieji_url = set()
    for puslapis in range(1, 10):
        rss_urls = [
            (
                f"https://www.bernardinai.lt/feed/{feed_slug}/?paged={puslapis}"
                if puslapis > 1
                else f"https://www.bernardinai.lt/feed/{feed_slug}/"
            ),
            (
                f"https://www.bernardinai.lt/?feed={feed_slug}&paged={puslapis}"
                if puslapis > 1
                else f"https://www.bernardinai.lt/?feed={feed_slug}"
            ),
        ]

        pasiektas_feed = None
        paskutinis_kodas = 0
        paskutine_kl = ""

        for rss_url in rss_urls:
            feed, status_code, kl_msg = nuskaityti_rss_srauta(rss_url)
            paskutinis_kodas = status_code
            paskutine_kl = kl_msg
            if feed is not None:
                pasiektas_feed = feed
                break

        if pasiektas_feed is None:
            if puslapis > 1 and paskutinis_kodas == 404:
                break
            kritine_klaida(
                f"Nepavyko nuskaityti RSS srauto '{feed_slug}' (puslapis"
                f" {puslapis}): {paskutine_kl}"
            )

        if not pasiektas_feed.entries:
            break

        pirmas_link = getattr(pasiektas_feed.entries[0], "link", "")
        if pirmas_link in puslapio_pirmieji_url:
            break
        puslapio_pirmieji_url.add(pirmas_link)

        visi_senesni = True
        for entry in pasiektas_feed.entries:
            rez = apdoroti_straipsni(entry, is_main=is_main)
            if rez == "SENESNIS":
                continue
            visi_senesni = False
            if isinstance(rez, dict):
                tikslinis_sarasas.append(rez)

        if visi_senesni:
            break


print("Nuskaitomas pagrindinis RSS srautas (Religija)...")
surinkti_srauto_straipsnius(
    "mailerlite-religija", True, pagrindiniai_straipsniai
)

print("Nuskaitomas papildomas Religijos RSS srautas...")
surinkti_srauto_straipsnius(
    "mailerlite-religija-visi", False, kiti_straipsniai
)

pagrindiniai_straipsniai.sort(key=lambda x: x["pub_date_obj"])
kiti_straipsniai.sort(key=lambda x: x["pub_date_obj"])

viso_straipsniu = len(pagrindiniai_straipsniai) + len(kiti_straipsniai)
print(
    f"Iš viso atrinkta: {len(pagrindiniai_straipsniai)} pagrindinių ir"
    f" {len(kiti_straipsniai)} papildomų straipsnių."
)

if len(pagrindiniai_straipsniai) < MIN_PAGRINDINIAI_STR:
    kritine_klaida(
        f"Rasta per mažai pagrindinių straipsnių"
        f" ({len(pagrindiniai_straipsniai)}, reikalaujama bent"
        f" {MIN_PAGRINDINIAI_STR})!"
    )

if viso_straipsniu < MIN_VISO_STR:
    kritine_klaida(
        f"Iš viso rasta tik {viso_straipsniu} straipsnių (reikalaujama bent"
        f" {MIN_VISO_STR}). Galimai nepilnas srautas!"
    )

# =========================================================================
# GRIEŽTA VISŲ NUOTRAUKŲ PATIKRA IR PARUOŠIMAS (BASE64 PDF + EMAIL URL)
# =========================================================================
print("Tikrinamos ir parsiunčiamos visos leidinio nuotraukos...")

visi_straipsniai = pagrindiniai_straipsniai + kiti_straipsniai
for str_item in visi_straipsniai:
    if not str_item.get("image"):
        rastas = rasti_nuotrauka_per_wp_api(str_item["link"])
        if rastas:
            str_item["image"] = rastas
        else:
            kritine_klaida(
                f"Straipsnis „{str_item['title']}“ neturi titulinės nuotraukos!"
            )

    img_info = parsiusti_ir_patikrinti_nuotrauka(
        str_item["image"], kontekstas=f"Straipsnis: {str_item['title']}"
    )
    str_item["pdf_image_src"] = img_info["data_uri"]
    str_item["email_image_url"] = img_info["email_url"]
    str_item["raw_image_bytes"] = img_info["bytes"]
    str_item["raw_image_mime"] = img_info["mime"]

    def pakeisti_vidini_img(match):
        pilna_zyma = match.group(0)
        src_m = re.search(r'src=["\']([^"\']+)["\']', pilna_zyma, re.I)
        if not src_m:
            return ""
        vid_info = parsiusti_ir_patikrinti_nuotrauka(
            src_m.group(1),
            kontekstas=f"Vidinė iliustracija straipsnyje: {str_item['title']}",
        )
        svari_zyma = re.sub(
            r'\s+(?:srcset|sizes|loading|decoding)=["\'][^"\']*["\']',
            "",
            pilna_zyma,
            flags=re.I,
        )
        svari_zyma = re.sub(
            r'src=["\'][^"\']+["\']',
            f'src="{vid_info["data_uri"]}"',
            svari_zyma,
            count=1,
            flags=re.I,
        )
        return svari_zyma

    if "<img" in str_item["content"].lower():
        str_item["content"] = re.sub(
            r"<img\b[^>]*>",
            pakeisti_vidini_img,
            str_item["content"],
            flags=re.I,
        )

cover_article = pagrindiniai_straipsniai[-1]
cover_bg_data_uri = cover_article["pdf_image_src"]
cover_article_title = cover_article["title"]
cover_raw_bytes = cover_article["raw_image_bytes"]
cover_raw_mime = cover_article["raw_image_mime"]

print(
    f">>> Visos nuotraukos ({len(nuotrauku_podelis)} unikalios) sėkmingai"
    " patikrintos ir paruoštos!"
)

# =========================================================================
# PDF HTML FORMAVIMAS IR GENERAVIMAS
# =========================================================================
reklamos_indeksas = 0
THEME_COLOR = "#2b5c8f"

html_kodas = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 20mm 15mm 20mm 15mm;
        @bottom-center {{
            content: counter(page); font-family: 'Georgia', serif; font-size: 11pt; color: {THEME_COLOR};
        }}
    }}
    @page cover {{ margin: 0; @bottom-center {{ content: none; }} }}
    html, body {{ margin: 0; padding: 0; }}
    body {{ font-family: 'Georgia', serif; color: #222; line-height: 1.6; font-size: 11pt; }}
    
    .cover-page {{ page: cover; position: relative; width: 210mm; height: 297mm; background-color: #1a1a1a; overflow: hidden; }}
    .bg-img {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }}
    .gradient-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,0.02) 25%, rgba(0,0,0,0.08) 40%, rgba(0,0,0,0.22) 55%, rgba(0,0,0,0.48) 70%, rgba(0,0,0,0.76) 84%, rgba(0,0,0,0.92) 93%, rgba(12,12,12,0.98) 100%); z-index: 2; }}
    
    .top-bar {{ position: absolute; top: 0; left: 0; width: 100%; background-color: #ffffff; text-align: center; padding: 25px 0; z-index: 5; border-bottom: 3px solid {THEME_COLOR}; }}
    .logo-main {{ max-width: 240px; display: inline-block; vertical-align: middle; }}
    
    .cover-bottom-content {{ position: absolute; bottom: 50px; left: 0; width: 100%; text-align: center; color: white; z-index: 5; }}
    .main-title {{ font-size: 36pt; font-weight: bold; margin-bottom: 15px; letter-spacing: 2px; text-transform: uppercase; line-height: 1.15; text-shadow: 0 4px 15px rgba(0,0,0,0.6); }}
    .divider {{ width: 100px; height: 3px; background-color: {THEME_COLOR}; margin: 0 auto 20px auto; }}
    .sub-title {{ font-size: 18pt; color: #E0E0E0; margin-bottom: 35px; font-style: italic; text-shadow: 0 2px 8px rgba(0,0,0,0.6); }}
    
    .meta-footer {{ font-size: 9.5pt; text-transform: uppercase; line-height: 1.6; color: #d4d4d4; padding-top: 18px; border-top: 1px solid rgba(255,255,255,0.2); width: 85%; margin: 0 auto; }}
    
    .toc-page {{ page-break-before: always; page-break-after: always; padding-top: 10mm; }}
    .toc-title {{ text-align: center; font-size: 24pt; color: {THEME_COLOR}; text-transform: uppercase; margin-bottom: 30px; margin-top: 20px; }}
    .toc-list {{ list-style: none; padding: 0; margin: 0; }}
    .toc-item {{ border-bottom: 1px dotted #ccc; margin-bottom: 15px; padding-bottom: 5px; overflow: hidden; }}
    .toc-link {{ text-decoration: none; color: #222; display: block; }}
    .toc-author {{ font-size: 9.5pt; color: #666; font-style: italic; font-weight: normal; margin-left: 6px; }}
    .toc-section-title {{ font-size: 14pt; color: {THEME_COLOR}; font-weight: bold; text-transform: uppercase; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid {THEME_COLOR}; padding-bottom: 5px; }}
    .intro-box {{ background-color: #f9f9f9; padding: 30px; border-radius: 8px; border: 1px solid #eaeaea; margin: 35px auto 30px auto; max-width: 500px; text-align: center; }}
    .btn-support {{ display: inline-block; background-color: {THEME_COLOR}; color: #FFF; padding: 10px 20px; text-decoration: none; font-weight: bold; border-radius: 4px; margin-top: 15px; }}
    
    .article-columns {{ column-count: 2; column-gap: 30px; text-align: justify; }}
    .drop-cap {{ font-size: 350%; float: left; margin: 4px 8px 0 0; color: {THEME_COLOR}; line-height: 0.8; font-weight: bold; }}
    .article-columns p {{ margin-top: 0; margin-bottom: 15px; widows: 2; orphans: 2; }}
    
    .article-page {{ margin-top: 40px; padding-top: 30px; border-top: 1px solid #cccccc; }}
    .article-page:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
    .article-top-block {{ break-inside: avoid; page-break-inside: avoid; break-after: avoid; page-break-after: avoid; margin-bottom: 25px; }}
    .article-header {{ text-align: center; margin-bottom: 20px; }}
    .article-title {{ font-size: 26pt; font-weight: bold; margin-bottom: 10px; line-height: 1.2; }}
    .article-meta {{ font-size: 10pt; color: #666; text-transform: uppercase; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
    .article-image {{ width: 100%; max-height: 400px; object-fit: cover; margin-top: 15px; border-radius: 4px; }}
    
    .other-articles-section {{ page-break-before: always; padding-top: 10mm; }}
    .other-section-header {{ text-align: center; font-size: 24pt; font-weight: bold; color: {THEME_COLOR}; text-transform: uppercase; margin-bottom: 10px; border-bottom: 2px solid {THEME_COLOR}; padding-bottom: 10px; }}
    .other-section-subtitle {{ text-align: center; font-size: 10pt; color: #666; margin-bottom: 30px; font-style: italic; padding: 0 10%; line-height: 1.5; }}
    .other-article {{ margin-bottom: 40px; }}
    .other-article-top-block {{ break-inside: avoid; page-break-inside: avoid; break-after: avoid; page-break-after: avoid; margin-bottom: 15px; }}
    .other-article-title {{ font-size: 16pt; font-weight: bold; margin-bottom: 8px; line-height: 1.2; color: #111; }}
    .other-article-meta {{ font-size: 9pt; color: #666; text-transform: uppercase; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
    .other-article img {{ width: 100% !important; height: auto !important; max-height: 300px; object-fit: cover; border-radius: 4px; margin-bottom: 5px; }}
    .other-article figure, .other-article .wp-caption {{ margin: 0 0 15px 0; width: 100% !important; break-inside: avoid; page-inside: avoid; }}
    .other-article figcaption, .other-article .wp-caption-text {{ font-size: 8pt; color: #777; font-style: italic; text-align: center; line-height: 1.3; margin-top: 5px; }}
    
    .ad-box {{ margin: 35px auto 20px auto; padding: 16px 24px; background-color: #fcfcfc; border: 1px dashed #cccccc; border-radius: 6px; text-align: center; max-width: 420px; break-inside: avoid; page-break-inside: avoid; }}
    .ad-title {{ font-size: 10pt; font-weight: bold; color: #444444; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }}
    .ad-contact {{ font-size: 9.5pt; color: #666666; }}
    .ad-contact a {{ color: {THEME_COLOR}; text-decoration: none; font-weight: bold; }}
    
    .back-to-toc {{ text-align: right; margin-top: 15px; font-size: 9pt; }}
    .back-to-toc a {{ color: {THEME_COLOR}; text-decoration: none; }}
    .contacts-page {{ page-break-before: always; padding-top: 10mm; }}
</style>
</head>
<body>
    <div class="cover-page">
        <img src="{cover_bg_data_uri}" class="bg-img">
        <div class="gradient-overlay"></div>
        
        <div class="top-bar">
            <img src="{logo_src}" class="logo-main">
        </div>
        
        <div class="cover-bottom-content">
            <div class="main-title">Religijos naujienų ir<br>tikėjimo savaitraštis</div>
            <div class="divider"></div>
            <div class="sub-title">Geriausi savaitės tekstai vienoje vietoje</div>
            
            <div class="meta-footer">
                <div><strong>DATA:</strong> {leidinio_data} &nbsp;&nbsp;|&nbsp;&nbsp; <strong>NUMERIS:</strong> {leidinio_numeris}</div>
                <div style="margin-top: 4px;"><strong>LAIKOTARPIS:</strong> {savaites_laikotarpis}</div>
                <div style="margin-top: 10px; font-size: 8.5pt; opacity: 0.75;">ISSN 3120-9742</div>
            </div>
        </div>
    </div>

    <div class="toc-page" id="turinys">
        <div class="toc-title">Turinys</div>
        <div class="toc-section-title">Savaitės svarbiausi</div>
        <ul class="toc-list">
"""

for i, straipsnis in enumerate(pagrindiniai_straipsniai):
    autoriaus_span = (
        '<span class="toc-author" style="text-transform:'
        f' uppercase;">{straipsnis["author"]}. </span>'
        if straipsnis["author"]
        else ""
    )
    html_kodas += (
        f'<li class="toc-item"><a href="#pagrindinis_{i}"'
        f' class="toc-link">{autoriaus_span}<strong>{straipsnis["title"]}</strong></a></li>'
    )

if kiti_straipsniai:
    html_kodas += """
        </ul>
        <div class="toc-section-title">Kiti savaitės religijos ir tikėjimo tekstai</div>
        <ul class="toc-list">
"""
    for i, straipsnis in enumerate(kiti_straipsniai):
        autoriaus_span = (
            '<span class="toc-author" style="text-transform:'
            f' uppercase;">{straipsnis["author"]}. </span>'
            if straipsnis["author"]
            else ""
        )
        html_kodas += (
            f'<li class="toc-item"><a href="#kitas_{i}"'
            f' class="toc-link">{autoriaus_span}<strong>{straipsnis["title"]}</strong></a></li>'
        )

html_kodas += f"""
        </ul>
        {f'<div style="background-color: #fcfcfc; border-left: 4px solid {THEME_COLOR}; padding: 12px 18px; margin: 35px auto 10px auto; max-width: 464px; font-size: 10pt; color: #444; font-style: italic; text-align: center;">{ankstesnio_nr_tekstas}</div>' if ankstesnio_nr_tekstas else ''}
        <div class="intro-box">
            <h3 style="margin-top: 0; color: #222; font-size: 16pt;">Palaikykite mūsų veiklą</h3>
            <p style="color: #555;">Bernardinai.lt yra nepriklausomas leidinys, savo misiją tęsiantis išskirtinai skaitytojų paramos dėka. Kviečiame mus paremti.</p>
            <a href="https://www.bernardinai.lt/parama" class="btn-support">Paremkite mus</a>
        </div>
    </div>
"""

for i, straipsnis in enumerate(pagrindiniai_straipsniai):
    meta_parts = []
    if straipsnis["author"]:
        meta_parts.append(f"<strong>{straipsnis['author']}</strong>")
    if straipsnis["source"]:
        meta_parts.append(f"<strong>{straipsnis['source']}</strong>")
    meta_parts.append(f"Publikuota: {straipsnis['date']}")
    meta_eilute = " &nbsp;|&nbsp; ".join(meta_parts)

    html_kodas += (
        f"""
    <div class="article-page" id="pagrindinis_{i}">
        <div class="article-top-block">
            <div class="article-header">
                <div class="article-title">{straipsnis['title']}</div>
                <div class="article-meta">{meta_eilute}</div>
            </div>
            <img src="{straipsnis['pdf_image_src']}" class="article-image">
        </div>
        <div class="article-columns">
            {straipsnis['content']}
        </div>
        """
        + gauti_reklamos_bloka("religija", reklamos_indeksas, "pdf")
        + """
        <div class="back-to-toc"><a href="#turinys">↑ Grįžti į turinį</a></div>
    </div>
    """
    )
    reklamos_indeksas += 1

if kiti_straipsniai:
    html_kodas += """
    <div class="other-articles-section">
        <div class="other-section-header">Kiti savaitės religijos ir tikėjimo tekstai</div>
        <div class="other-section-subtitle">Čia rasite Bernardinai.lt redaktorių ir žurnalistų atrinktas svarbiausias savaitės religinio gyvenimo bei dvasingumo naujienas, tekstus ir pokalbius.</div>
        <div class="article-columns">
    """
    for i, straipsnis in enumerate(kiti_straipsniai):
        meta_parts = []
        if straipsnis["author"]:
            meta_parts.append(f"<strong>{straipsnis['author']}</strong>")
        if straipsnis["source"]:
            meta_parts.append(f"<strong>{straipsnis['source']}</strong>")
        meta_parts.append(f"Publikuota: {straipsnis['date']}")
        meta_eilute = " &nbsp;|&nbsp; ".join(meta_parts)

        html_kodas += (
            f"""
            <div class="other-article" id="kitas_{i}">
                <div class="other-article-top-block">
                    <div class="other-article-title">{straipsnis['title']}</div>
                    <div class="other-article-meta">{meta_eilute}</div>
                </div>
                {straipsnis['content']}
                """
            + gauti_reklamos_bloka("religija", reklamos_indeksas, "pdf")
            + """
                <div class="back-to-toc"><a href="#turinys">↑ Grįžti į turinį</a></div>
            </div>
        """
        )
        reklamos_indeksas += 1
    html_kodas += """
        </div>
    </div>
    """

html_kodas += f"""
    <div class="contacts-page">
        <h1 style="border-bottom: 2px solid {THEME_COLOR}; padding-bottom: 10px; margin-bottom: 20px; font-size: 24pt; color: #111; text-transform: uppercase;">Redakcija ir kontaktai</h1>
        <div style="font-size: 11pt; line-height: 1.6; margin-bottom: 30px; text-align: left;">
            <strong>Interneto dienraštis „Bernardinai.lt“</strong><br>
            Veiklos pradžia – 2004 m. vasario 21 d.<br><br>
            ISSN 3120-9742<br><br>
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
                    <p><strong>Inga Bartulevičiūtė</strong><br>Redaktorė<br>inga.bartuleviciute@bernardinai.lt</p>
                    <p><strong>Rita Bagdonaitė</strong><br>Redaktorė<br>rita.bagdonaite@bernardinai.lt</p>
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


class WeasyPrintImageErrorWatcher(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.image_errors = []

    def emit(self, record):
        msg = self.format(record)
        if "image" in msg.lower() or "failed to load" in msg.lower():
            self.image_errors.append(msg)


wp_logger = logging.getLogger("weasyprint")
img_watcher = WeasyPrintImageErrorWatcher()
wp_logger.addHandler(img_watcher)

print(f"Generuojamas PDF failas: {pdf_archyvas}...")
try:
    HTML(string=html_kodas, url_fetcher=weasyprint_url_fetcher).write_pdf(
        pdf_archyvas
    )
except Exception:
    traceback.print_exc()
    kritine_klaida("Nepavyko sugeneruoti PDF failo!")

if img_watcher.image_errors:
    kritine_klaida(
        "WeasyPrint pranešė apie neįkeltus paveikslėlius PDF viduje:"
        f" {img_watcher.image_errors[0]}"
    )

if not os.path.exists(pdf_archyvas) or os.path.getsize(pdf_archyvas) < 50000:
    kritine_klaida("Sugeneruotas PDF failas yra tuščias arba per mažas!")

pdf_dydis_vietinis = os.path.getsize(pdf_archyvas)
print(
    f">>>> Sėkmingai sukurta: {pdf_archyvas}"
    f" ({pdf_dydis_vietinis / (1024 * 1024):.2f} MB)"
)

# =========================================================================
# 1 ŽINGSNIS: FTP ĮKĖLIMAS SU 3 BANDYMŲ APSAUGA IR DYDŽIO PATIKRA
# =========================================================================
if is_real_run:
    print(f">>> Pradedamas PDF failo kėlimas į FTP serverį ({ftp_server})...")
    import ftplib

    ftp_uploaded = False
    paskutine_ftp_kl = ""

    for attempt in range(1, 4):
        try:
            print(f"Bandymas {attempt}/3 jungtis prie FTP...")
            ftp = ftplib.FTP(timeout=45)
            ftp.connect(ftp_server, 21)
            ftp.login(user=ftp_user, passwd=ftp_pass)
            ftp.set_pasv(True)

            try:
                ftp.cwd(str(current_year))
            except ftplib.error_perm:
                ftp.mkd(str(current_year))
                ftp.cwd(str(current_year))

            filename = os.path.basename(pdf_archyvas)
            esami_failai = []
            try:
                esami_failai = ftp.nlst()
            except Exception:
                pass

            if filename in esami_failai:
                print(
                    f">>> FTP serveryje jau yra '{filename}' – failas bus"
                    " perrašytas (atnaujintas)."
                )

            with open(pdf_archyvas, "rb") as file:
                ftp.storbinary(f"STOR {filename}", file)

            try:
                ftp.voidcmd("TYPE I")
                serverio_dydis = ftp.size(filename)
                if serverio_dydis is not None and serverio_dydis < 50000:
                    ftp.quit()
                    raise RuntimeError(
                        f"FTP serveryje įkeltas failas per mažas ({serverio_dydis} B)!"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

            ftp.quit()
            print(f">>> Sėkmingai įkelta / atnaujinta FTP serveryje: {filename}")
            ftp_uploaded = True
            break
        except Exception as e:
            paskutine_ftp_kl = str(e)
            print(f"Klaida FTP bandyme {attempt}: {e}")
            if attempt < 3:
                time.sleep(5)

    if not ftp_uploaded:
        kritine_klaida(
            f"Nepavyko įkelti PDF į FTP serverį po 3 bandymų: {paskutine_ftp_kl}"
        )

pdf_url = (
    f"https://www.bernardinai.lt/savaitrastis/{current_year}/"
    f"religijos_savaitrastis_{today_str}.pdf"
)

# =========================================================================
# 2 ŽINGSNIS: WORDPRESS PUBLIKAVIMAS ARBA ATNAUJINIMAS (PRIEŠ NAUJIENLAIŠKĮ!)
# =========================================================================
wp_religija_cat_id = 16  # Pagrindinė Religijos rubrika
wp_savaitrastis_cat_id = int(os.environ.get("WP_CATEGORY_ID_RELIGIJA", "").strip() or 65204)
wp_acf_author_id = 8149


def gauti_arba_sukurti_zyma(tag_name, headers):
    encoded_name = urllib.parse.quote(tag_name)
    url = f"https://www.bernardinai.lt/wp-json/wp/v2/tags?search={encoded_name}&per_page=50"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
            for t in tags:
                if t.get("name", "").strip().lower() == tag_name.strip().lower():
                    return int(t["id"])
    except Exception as e:
        print(f">>> Įspėjimas ieškant žymos '{tag_name}': {e}")

    try:
        create_url = "https://www.bernardinai.lt/wp-json/wp/v2/tags"
        payload = json.dumps({"name": tag_name}).encode("utf-8")
        h = headers.copy()
        h["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(
            create_url, data=payload, headers=h, method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            new_tag = json.loads(resp.read().decode("utf-8"))
            return int(new_tag["id"])
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
            if err_json.get("code") == "term_exists":
                term_id = err_json.get("data", {}).get("term_id")
                if term_id:
                    return int(term_id)
        except Exception:
            pass
    except Exception:
        pass
    return None


if wp_rezimas in ("publish", "draft"):
    print(
        f"Ruošiamas informacinis įrašas Bernardinai.lt svetainėje"
        f" (statusas: {wp_rezimas})..."
    )

    raktazodziai = [
        "Bernardinai.lt religijos naujienų ir tikėjimo savaitraštis",
        "tikėjimo savaitraštis",
        "religija",
        "tikėjimas",
        "krikščionybė",
    ]
    tag_ids = []
    for kw in raktazodziai:
        tid = gauti_arba_sukurti_zyma(kw, wp_headers)
        if tid and tid not in tag_ids:
            tag_ids.append(tid)

    irasas_pavadinimas = (
        "Religijos naujienų ir tikėjimo savaitraštis Nr."
        f" {leidinio_numeris} | {leidinio_data}"
    )
    focus_keyphrase = "tikėjimo savaitraštis"
    seo_title = (
        f"Religijos ir tikėjimo savaitraštis Nr. {leidinio_numeris} |"
        " Bernardinai.lt"
    )
    meta_aprasymas = (
        "Naujausias „Bernardinai.lt“ religijos ir tikėjimo savaitraštis (Nr."
        f" {leidinio_numeris}). Svarbiausi savaitės tekstai PDF formatu."
    )[:140]

    nuotraukos_alt = (
        "Bernardinai.lt religijos naujienų ir tikėjimo savaitraštis Nr."
        f" {leidinio_numeris}"
    )
    nuotraukos_antraste = (
        "„Bernardinai.lt“ religijos naujienų ir tikėjimo savaitraštis (Nr."
        f" {leidinio_numeris}). Viršelyje – iliustracija straipsniui"
        f" „{cover_article_title}“."
    )

    featured_media_id = None
    try:
        ext = ".png" if cover_raw_mime == "image/png" else ".jpg"
        failo_varda = f"religijos_savaitrastis_cover_{today_str}{ext}"
        media_headers = wp_headers.copy()
        media_headers["Content-Type"] = cover_raw_mime
        media_headers["Content-Disposition"] = (
            f'attachment; filename="{failo_varda}"'
        )

        req_media = urllib.request.Request(
            "https://www.bernardinai.lt/wp-json/wp/v2/media",
            data=cover_raw_bytes,
            headers=media_headers,
            method="POST",
        )
        with urllib.request.urlopen(req_media, timeout=30) as resp_media:
            media_json = json.loads(resp_media.read().decode("utf-8"))
            featured_media_id = media_json.get("id")
            print(
                ">>> Titulinė nuotrauka sėkmingai įkelta į WP! ID:"
                f" {featured_media_id}"
            )

        if featured_media_id:
            media_meta_payload = {
                "title": irasas_pavadinimas,
                "alt_text": nuotraukos_alt,
                "caption": nuotraukos_antraste,
                "description": nuotraukos_antraste,
            }
            meta_update_headers = wp_headers.copy()
            meta_update_headers["Content-Type"] = (
                "application/json; charset=utf-8"
            )
            req_media_update = urllib.request.Request(
                f"https://www.bernardinai.lt/wp-json/wp/v2/media/{featured_media_id}",
                data=json.dumps(media_meta_payload).encode("utf-8"),
                headers=meta_update_headers,
                method="POST",
            )
            urllib.request.urlopen(req_media_update, timeout=20).close()
    except Exception as e:
        kritine_klaida(
            f"Nepavyko įkelti viršelio nuotraukos į WordPress Media biblioteką: {e}"
        )

    if not featured_media_id:
        kritine_klaida("WordPress Media biblioteka negrąžino nuotraukos ID!")

    temu_sarasas_html = "<h3>Šiame numeryje skaitykite:</h3><ul>"
    for s in pagrindiniai_straipsniai:
        temu_sarasas_html += (
            f'<li><strong>{s["author"]}</strong>: <a'
            f' href="{s["link"]}">{s["title"]}</a></li>'
        )
    temu_sarasas_html += "</ul>"

    wp_html_turinys = f"""<p>Skaitytojams pateikiame interneto dienraščio „Bernardinai.lt“ <strong>religijos naujienų ir tikėjimo savaitraščio</strong> numerį ({leidinio_data}, Nr. {leidinio_numeris}). Šiame leidinyje rasite redaktorių atrinktus svarbiausius savaitės religijos, dvasingumo ir krikščioniško gyvenimo tekstus bei pokalbius. Leidinys paruoštas patogiam skaitymui žurnalo formatu.</p>
{temu_sarasas_html}
<p style="margin: 30px 0; text-align: center;">
    <a href="{pdf_url}" target="_blank" rel="noopener noreferrer" style="background-color: {THEME_COLOR}; color: #ffffff; padding: 14px 28px; text-decoration: none; font-weight: bold; border-radius: 5px; display: inline-block; font-size: 16px;">
        Atsisiųsti PDF savaitraštį
    </a>
</p>"""

    kategorijos_sarasas = [wp_religija_cat_id]
    if wp_savaitrastis_cat_id not in kategorijos_sarasas:
        kategorijos_sarasas.append(wp_savaitrastis_cat_id)

    norimas_slug = (
        f"religijos-savaitrastis-nr-{current_year}-{numeris}-{today_str}"
        if paleidimo_rezimas != "bandomasis" or custom_num_raw
        else f"religijos-savaitrastis-bandomasis-{today_str}"
    )

    payload_wp = {
        "title": irasas_pavadinimas,
        "slug": norimas_slug,
        "content": wp_html_turinys,
        "excerpt": meta_aprasymas,
        "status": wp_rezimas,
        "featured_media": int(featured_media_id),
        "categories": kategorijos_sarasas,
        "tags": tag_ids,
        "acf": {
            "short_description": meta_aprasymas,
            "author": [wp_acf_author_id],
            "show_on_homepage": "yes",
            "show_in_newest_posts": "no",
            "show_on_homepage_media": "no",
            "show_in_main_posts": 0,
            "post_featured_image": "1",
        },
        "meta": {
            "_yoast_wpseo_focuskw": focus_keyphrase,
            "_yoast_wpseo_title": seo_title,
            "_yoast_wpseo_metadesc": meta_aprasymas,
            "short_description": meta_aprasymas,
            "show_on_homepage": "yes",
            "show_in_newest_posts": "no",
            "post_featured_image": "1",
        },
    }

    esamo_wp_id = None
    try:
        check_u = (
            "https://www.bernardinai.lt/wp-json/wp/v2/posts"
            f"?slug={urllib.parse.quote(norimas_slug)}&status=any"
        )
        req_chk = urllib.request.Request(check_u, headers=wp_headers)
        with urllib.request.urlopen(req_chk, timeout=20) as r_chk:
            rasti_ir = json.loads(r_chk.read().decode("utf-8"))
            if rasti_ir and isinstance(rasti_ir, list):
                esamo_wp_id = rasti_ir[0].get("id")
    except Exception:
        pass

    wp_post_url = (
        f"https://www.bernardinai.lt/wp-json/wp/v2/posts/{esamo_wp_id}"
        if esamo_wp_id
        else "https://www.bernardinai.lt/wp-json/wp/v2/posts"
    )

    post_headers = wp_headers.copy()
    post_headers["Content-Type"] = "application/json; charset=utf-8"

    req_wp = urllib.request.Request(
        wp_post_url,
        data=json.dumps(payload_wp).encode("utf-8"),
        headers=post_headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req_wp, timeout=30) as resp_wp:
            wp_data = json.loads(resp_wp.read().decode("utf-8"))
            post_link = wp_data.get("link", "Nuoroda nerasta")
            veiksmas_txt = "atnaujintas" if esamo_wp_id else "sukurtas"
            print(
                f">>> Sėkmingai {veiksmas_txt} WordPress įrašas! URL: {post_link}"
            )
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        kritine_klaida(
            f"Nepavyko publikuoti įrašo WordPress (kodas {e.code}): {err_msg}"
        )
    except Exception as e:
        kritine_klaida(f"Nepavyko publikuoti įrašo WordPress: {e}")
else:
    print(">>> WordPress įrašo kūrimas praleistas pagal pasirinktą režimą.")

# =========================================================================
# 3 ŽINGSNIS: MAILERLITE NAUJIENLAIŠKIO KŪRIMAS / SIUNTIMAS
# =========================================================================
if nl_rezimas in ("siusti", "juodrastis"):
    print(f"Ruošiamas MailerLite laiškas (režimas: {nl_rezimas})...")

    email_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Savaitraštis</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f4;">
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <img src="https://raw.githubusercontent.com/Bernardinai/bernardinai/main/logo.png" alt="Bernardinai.lt" style="max-width: 200px;">
        </div>
        <h1 style="text-align: center; color: #111; font-size: 24px;">Naujausias „Bernardinai.lt“ Religijos naujienų ir tikėjimo savaitraštis jau paruoštas!</h1>
        <p style="text-align: center; color: #555; font-size: 16px;">Sveiki, paruošėme jums {leidinio_data} geriausių tekstų rinkinį žurnalo formatu.</p>
        
        <div style="text-align: center; margin: 40px 0;">
            <a href="{pdf_url}" style="background-color: {THEME_COLOR}; color: #ffffff; padding: 15px 30px; text-decoration: none; font-size: 18px; font-weight: bold; border-radius: 5px; display: inline-block;">Atsisiųsti PDF savaitraštį</a>
        </div>
        
        <h2 style="color: {THEME_COLOR}; border-bottom: 2px solid {THEME_COLOR}; padding-bottom: 10px; margin-top: 40px;">Savaitės svarbiausi</h2>
    """

    for straipsnis in pagrindiniai_straipsniai:
        meta_parts_mail = []
        if straipsnis["author"]:
            meta_parts_mail.append(straipsnis["author"])
        if straipsnis["source"]:
            meta_parts_mail.append(straipsnis["source"])
        meta_parts_mail.append(f"Publikuota: {straipsnis['date']}")
        meta_mail_eilute = " | ".join(meta_parts_mail)

        email_html += f"""
        <div style="margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid #eee;">
            <img src="{straipsnis['email_image_url']}" alt="{straipsnis['title']}" style="width: 100%; max-width: 600px; border-radius: 8px; margin-bottom: 15px;">
            <h3 style="margin: 0 0 10px 0;"><a href="{straipsnis['link']}" style="color: #111; text-decoration: none; font-size: 20px;">{straipsnis['title']}</a></h3>
            <div style="color: {THEME_COLOR}; font-size: 12px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">{meta_mail_eilute}</div>
            <p style="color: #555; font-size: 15px; line-height: 1.5; margin: 0;">{straipsnis['excerpt']}</p>
        </div>
        """

    if kiti_straipsniai:
        email_html += f"""
        <h2 style="color: {THEME_COLOR}; border-bottom: 2px solid {THEME_COLOR}; padding-bottom: 10px; margin-top: 40px;">Kiti savaitės tekstai</h2>
        <p style="color: #666; font-size: 13px; font-style: italic; margin-bottom: 20px;">Čia rasite Bernardinai.lt redaktorių ir žurnalistų atrinktus svarbiausius savaitės tekstus ir interviu.</p>
        """
        for straipsnis in kiti_straipsniai:
            meta_parts_mail = []
            if straipsnis["author"]:
                meta_parts_mail.append(straipsnis["author"])
            if straipsnis["source"]:
                meta_parts_mail.append(straipsnis["source"])
            meta_parts_mail.append(f"Publikuota: {straipsnis['date']}")
            meta_mail_eilute = " | ".join(meta_parts_mail)

            email_html += f"""
            <div style="margin-bottom: 40px; padding-bottom: 20px; border-bottom: 1px solid #eee;">
                <img src="{straipsnis['email_image_url']}" alt="{straipsnis['title']}" style="width: 100%; max-width: 600px; border-radius: 8px; margin-bottom: 15px;">
                <h3 style="margin: 0 0 10px 0;"><a href="{straipsnis['link']}" style="color: #111; text-decoration: none; font-size: 20px;">{straipsnis['title']}</a></h3>
                <div style="color: {THEME_COLOR}; font-size: 12px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">{meta_mail_eilute}</div>
                <p style="color: #555; font-size: 15px; line-height: 1.5; margin: 0;">{straipsnis['excerpt']}</p>
            </div>
            """

    email_html += gauti_reklamos_bloka("religija", reklamos_indeksas, "email")
    email_html += f"""
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 12px; color: #999;">
            ISSN 3120-9742<br>
            © {current_year} VŠĮ BERNARDINAI.LT. Visos teisės saugomos.<br>
            Išsiųsta naudojant Bernardinai.lt automatizaciją.<br><br>
            <a href="{{$url}}" style="color: #999; text-decoration: underline;">Peržiūrėti naršyklėje</a> &nbsp;|&nbsp; 
            <a href="{{$unsubscribe}}" style="color: #999; text-decoration: underline;">Atsisakyti naujienlaiškio</a>
        </div>
    </div>
</body>
</html>
"""

    religija_group_id = int(
        os.environ.get("MAILERLITE_GROUP_ID_RELIGIJA", "").strip() or 103032162
    )
    payload_campaign = {
        "type": "regular",
        "groups": [religija_group_id],
        "subject": (
            f"Religijos naujienų ir tikėjimo savaitraštis | {leidinio_data}"
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
            "User-Agent": INTERNAL_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req_campaign, timeout=30) as response:
            campaign_data = json.loads(response.read().decode("utf-8"))
            campaign_id = campaign_data.get("id")
            print(f">>> MailerLite kampanija sukurta. ID: {campaign_id}")

            if not campaign_id:
                kritine_klaida("MailerLite negrąžino kampanijos ID!")

            payload_content = {
                "html": email_html,
                "plain": (
                    "Naujausias „Bernardinai.lt“ Religijos naujienų ir tikėjimo"
                    " savaitraštis jau paruoštas!\n\nAtsisiųsti PDF galite čia:"
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
                    "User-Agent": INTERNAL_USER_AGENT,
                },
                method="PUT",
            )

            with urllib.request.urlopen(req_content, timeout=30):
                print(">>> MailerLite laiško turinys įkeltas!")

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
                        ">>> MailerLite kampanija sėkmingai perkelta į OUTBOX"
                        " (pradėta siųsti prenumeratoriams)!"
                    )
            else:
                print(
                    ">>> MailerLite laiškas išsaugotas kaip Juodraštis (Draft)."
                )

    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        kritine_klaida(
            f"Klaida MailerLite API (kodas {e.code}): {error_msg}"
        )
    except SystemExit:
        raise
    except Exception as e:
        kritine_klaida(f"Klaida vykdant MailerLite veiksmus: {e}")
else:
    print(">>> MailerLite naujienlaiškio siuntimas išjungtas ('nesiusti').")

# =========================================================================
# 4 ŽINGSNIS: LEIDINIO NUMERIO IŠSAUGOJIMAS ATMINTYJE
# =========================================================================
if paleidimo_rezimas == "tikras":
    atnaujinti_skaitikli = (current_year > saved_year) or (
        current_year == saved_year and numeris >= saved_num
    )
    if atnaujinti_skaitikli:
        try:
            with open(tracker_file, "w", encoding="utf-8") as f:
                f.write(f"{current_year}/{numeris}/{today_str}")
            print(
                f">>> Leidinio numeris atnaujintas ir išsaugotas:"
                f" {current_year}/{numeris}/{today_str}"
            )
        except Exception as e:
            print(f"Nepavyko išsaugoti numerio failo: {e}")
    else:
        print(
            f">>> Išleistas ankstesnis numeris ({current_year}/{numeris}),"
            f" todėl pagrindinis skaitiklis ({saved_year}/{saved_num})"
            " nekeičiamas."
        )
elif paleidimo_rezimas == "tik_atnaujinti_pdf":
    print(
        ">>> REŽIMAS 'tik_atnaujinti_pdf': PDF failas FTP serveryje"
        " atnaujintas, numerio skaitiklis nekeičiamas."
    )
else:
    if not os.path.exists(tracker_file):
        try:
            with open(tracker_file, "w", encoding="utf-8") as f:
                f.write(f"{current_year}/0/2000-01-01")
        except Exception:
            pass
    print(
        ">>> BANDOMASIS PALEIDIMAS: Naudotas bandomasis režimas, skaitiklis"
        " neatnaujinamas."
    )
