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

# Jei paleista pagal tvarkaraštį (cron), siunčiame tik 18 val. Lietuvos laiku
if event_name == "schedule":
    if not auto_18val_enabled:
        print(
            ">>> Kasdienis automatinis siuntimas dar neįjungtas"
            " (AKTYVUOTI_KASDIENI_SIUNTIMA='ne'). Procesas sustabdytas."
        )
        sys.exit(0)
    if now_lt.hour != 18:
        print(
            f">>> Dabar Lietuvoje {now_lt.strftime('%H:%M')} val. Laukiama"
            " tikslaus 18:00 val. lango."
        )
        sys.exit(0)

raw_nl = (
    args.naujienlaiskis or os.environ.get("SIUSTI_NAUJIENLAISKI", "")
).strip().lower()

if not raw_nl or raw_nl == "auto":
    nl_rezimas = "siusti" if event_name == "schedule" else "juodrastis"
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
                        mail_subj = mails[0].get("subject", "") if isinstance(mails, list) and mails and isinstance(mails[0], dict) else ""
                        subj = str(c.get("subject") or mail_subj or c.get("name") or "")
                        created = str(c.get("date_created") or c.get("date_send") or "")
                        if "Dienos temos:" in subj and today_str in created:
                            return True
        except Exception:
            pass
    return False


if event_name == "schedule" and nl_rezimas == "siusti":
    if ar_siandien_jau_issiusta(api_key):
        print(">>> Šiandienos vakarinis naujienlaiškis jau išsiųstas! Stabdome.")
        sys.exit(0)


def uzkoduoti_url(url):
    if not url:
        return ""
    url = url.replace("&#038;", "&").replace("&amp;", "&").strip()
    parts = urllib.parse.urlsplit(url)
    clean_path = urllib.parse.quote(
        urllib.parse.unquote(parts.path), safe="/:@!$&'()*+,;=-._~"
    )
    clean_query = urllib.parse.quote(
        urllib.parse.unquote(parts.query), safe="=&:@!$'()*+,;-._~%"
    )
    return urllib.parse.urlunsplit(
        (parts.scheme or "https", parts.netloc, clean_path, clean_query, "")
    )


def email_img(raw_url, width=600, height=0):
    """Konvertuoja .webp į .jpg, kad nuotraukas rodytų visos el. pašto programos (įskaitant Outlook)."""
    clean = uzkoduoti_url(raw_url)
    if not clean:
        clean = "https://www.bernardinai.lt/wp-content/uploads/Bernardinai500x500-jpg-webp.webp"
    be_schemos = re.sub(r"^https?://", "", clean, flags=re.I)
    params = f"url={urllib.parse.quote(be_schemos, safe='')}&output=jpg&w={width}&q=85"
    if height > 0:
        params += f"&h={height}&fit=cover"
    return f"https://images.weserv.nl/?{params}"


def esc(text):
    return html.escape(str(text or "").strip())


def su_utm(url, saltinis_blokas):
    clean = uzkoduoti_url(url)
    if not clean:
        return "https://www.bernardinai.lt/"
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
            if isinstance(data, dict) and data.get("main_posts"):
                print(">>> Duomenys sėkmingai gauti iš /wp-json/custom/v1/daily-newsletter!")
                return data
    except urllib.error.HTTPError as e:
        print(
            f">>> Pastaba: specialus WP įskiepio adresas dar neaktyvus (HTTP {e.code})."
            " Naudojamas atsarginis standartinis WP REST API."
        )
    except Exception as e:
        print(
            f">>> Pastaba: nepavyko pasiekti specialaus WP mazgo ({e})."
            " Naudojamas atsarginis standartinis WP REST API."
        )
    return None


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

    def fetch_posts(params_str, limit=5):
        u = f"https://www.bernardinai.lt/wp-json/wp/v2/posts?{params_str}&_embed=1"
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
        "native_ads": [],
    }


duomenys = gauti_duomenis_is_wp_api()
if not duomenys:
    duomenys = gauti_atsarginius_duomenis_standartiniu_api()

main_posts = duomenys.get("main_posts") or []
if len(main_posts) < 2:
    kritine_klaida(
        f"Rasta per mažai pagrindinių straipsnių ({len(main_posts)}). Siuntimas stabdomas."
    )

quote = duomenys.get("quote")
editorials = duomenys.get("editorials") or []
most_read = duomenys.get("most_read") or []
categories = duomenys.get("categories") or []
posters = duomenys.get("posters") or []
native_ads = duomenys.get("native_ads") or []

print(
    f">>> Surinkta: {len(main_posts)} viršiniai, {len(editorials)} komentarai,"
    f" {len(most_read)} skaitomiausi, {len(categories)} rubrikos,"
    f" {len(posters)} afišos anonsai, citata: {'TAIP' if quote else 'NE'}."
)

# =========================================================================
# EL. LAIŠKO HTML FORMAVIMAS (600px, PRITAIKYTA MOBILIESIEMS IR OUTLOOK)
# =========================================================================
hero = main_posts[0]
secondary_main = main_posts[1:5]

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
  }}
</style>
</head>
<body style="margin:0; padding:0; background-color:{BG_PAGE}; font-family: Arial, Helvetica, sans-serif; color:{TEXT_MAIN}; -webkit-font-smoothing:antialiased;">
<div style="display:none; max-height:0; overflow:hidden; opacity:0;">
  {esc(hero.get('title'))} – svarbiausios „Bernardinai.lt“ dienos temos, komentarai ir rekomendacijos.
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

# 1. DIENOS CITATA
if quote and quote.get("text"):
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

# 2. PAGRINDINĖ DIENOS TEMA (HERO)
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

# 3. NUOMONĖS IR KOMENTARAI (SU APVALIOMIS AUTORIŲ NUOTRAUKOMIS)
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

# 4. SKAITOMIAUSI ŠIANDIEN
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

# REKLAMOS BANERIS (IŠ WP ACF ARBA REKLAMOS MODULIO)
if native_ads:
    ad = native_ads[0]
    ad_img = email_img(ad.get("image"), width=600)
    ad_url = ad.get("url", "https://www.bernardinai.lt/")
    html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 12px 28px;">
            <div style="font-size:10px; text-transform:uppercase; letter-spacing:1px; color:#999999; text-align:center; margin-bottom:4px;">Partnerių pasiūlymas</div>
            <a href="{esc(ad_url)}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;">
              <img src="{ad_img}" alt="{esc(ad.get('alt', 'Reklama'))}" width="544" style="display:block; width:100%; max-width:544px; height:auto; border-radius:6px; border:0;">
            </a>
          </td>
        </tr>
    """)
else:
    try:
        from reklamos import gauti_reklamos_bloka

        rek_html = gauti_reklamos_bloka("kasdienis", 0, "email")
        if rek_html:
            html_parts.append(f'<tr><td class="content-pad" style="padding: 8px 28px;">{rek_html}</td></tr>')
    except Exception:
        pass

# 5. RUBRIKŲ APŽVALGA (RELIGIJA, VISUOMENĖ, KULTŪRA, ŠEIMA, DIALOGAI)
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

# 6. AFIŠA – RENGINIAI IR KVIETIMAI
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

# 7. PARAMOS BLOKAS IR REKVIZITAI
parama_url = su_utm("https://www.bernardinai.lt/parama/", "footer_parama")
html_parts.append(f"""
        <tr>
          <td class="content-pad" style="padding: 26px 28px; background-color:{BRAND_DARK}; color:#ffffff; text-align:center;">
            <div style="font-family: Georgia, serif; font-size:20px; font-weight:bold; margin-bottom:8px;">Palaikykite nepriklausomą „Bernardinai.lt“ žurnalistiką</div>
            <p style="font-size:13px; line-height:1.55; color:#f2dedd; margin:0 0 18px 0;">
              „Bernardinai.lt“ negauna lėšų iš rinkliavų katalikiškai žiniasklaidai ir gyvuoja tik skaitytojų paramos dėka. Skirkite vienkartinę arba periodinę paramą.
            </p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:18px;">
              <tr>
                <td class="btn-col" align="center" style="padding:4px;">
                  <a href="{parama_url}" target="_blank" style="display:inline-block; background-color:#ffffff; color:{BRAND_DARK}; font-size:13px; font-weight:bold; text-decoration:none; padding:10px 16px; border-radius:4px;">Visi paramos būdai</a>
                </td>
                <td class="btn-col" align="center" style="padding:4px;">
                  <a href="{parama_url}#paysera" target="_blank" style="display:inline-block; background-color:{BRAND_ACCENT}; color:#ffffff; font-size:13px; font-weight:bold; text-decoration:none; padding:10px 16px; border-radius:4px;">Per Paysera / banką</a>
                </td>
                <td class="btn-col" align="center" style="padding:4px;">
                  <a href="{parama_url}#kortele" target="_blank" style="display:inline-block; background-color:#ffffff; color:{BRAND_DARK}; font-size:13px; font-weight:bold; text-decoration:none; padding:10px 16px; border-radius:4px;">Mokėjimo kortele</a>
                </td>
              </tr>
            </table>
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
    subject_line = f"{subject_prefix}Dienos temos: {hero.get('title', data_trumpiems)}"
    if len(subject_line) > 95:
        subject_line = subject_line[:92].rsplit(" ", 1)[0] + "…"

    payload_campaign = {
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
