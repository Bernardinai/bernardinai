import base64
import datetime
from datetime import timedelta, timezone
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import feedparser
from bs4 import BeautifulSoup

# --- KONFIGŪRACIJA ---
VATICAN_RSS_URL = "https://www.vaticannews.va/lt.rss.xml"
TRACKER_FILE = "vatican_publikuota.txt"
MAX_FEED_ITEMS_TO_CHECK = 5    # Tikriname tik 5 pačius naujausius RSS įrašus
MAX_AGE_HOURS = 24             # Neimame straipsnių, senesnių nei 24 valandos
MAX_ARTICLES_PER_RUN = 5       # Kiek daugiausia naujų straipsnių įkelti vieno paleidimo metu

# WordPress prisijungimai iš aplinkos kintamųjų (GitHub Secrets)
WP_USER = os.environ.get("WP_USERNAME", "")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
CF_KEY = os.environ.get("CF_AUTOMATION_KEY", "")

# Tikslūs Bernardinai.lt ID pagal jūsų nustatymus
WP_CATEGORY_ID = 24            # Rubrika: „Bažnyčia pasaulyje“
WP_ACF_AUTHOR_IDS = [858006, 8149]  # Autoriai: „Vatican News“ (858006) ir „Bernardinai.lt“ (8149)
WP_ACF_SOURCE_ID = 59898       # Šaltinis: „Vatican News“ (59898)
PUBLISH_STATUS = "draft"  # Visada įkelti kaip juodraštį patikrinimui

feedparser.USER_AGENT = "Bernardinai-Vatican-Bot/1.0"


def uzkrauti_publikuotus():
    if not os.path.exists(TRACKER_FILE):
        return set()
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def issaugoti_publikuota(url):
    with open(TRACKER_FILE, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")


def formuoti_meta_iki_140(tekstas):
    """Paruošia meta aprašymą iki 140 simbolių, teikiant pirmenybę pilnam baigtiniam sakiniui."""
    svarus = re.sub(r"<[^>]+>", "", tekstas).strip()
    svarus = re.sub(r"\s+", " ", svarus)
    if len(svarus) <= 140:
        return svarus

    kandidatas = svarus[:140]

    # 1. Bandome rasti paskutinį baigtinį sakinį (tašką, šauktuką ar klaustuką)
    sakinio_pabaigos = [m.end() for m in re.finditer(r'[.!?](?=\s|$)', kandidatas)]
    if sakinio_pabaigos and sakinio_pabaigos[-1] >= 45:
        return kandidatas[:sakinio_pabaigos[-1]].strip()

    # 2. Jei pirmas sakinys ilgesnis nei 140 simbolių, bandome kirpti ties kableliu ar brūkšniu
    skyrikliai = [m.start() for m in re.finditer(r'[,;–—](?=\s)', kandidatas)]
    if skyrikliai and skyrikliai[-1] >= 65:
        return kandidatas[:skyrikliai[-1]].strip() + "."

    # 3. Atsarginis variantas: kerpame ties paskutiniu pilnu žodžiu ir dedame tašką
    apkarpytas = svarus[:139]
    if " " in apkarpytas:
        apkarpytas = apkarpytas.rsplit(" ", 1)[0]
    return apkarpytas.rstrip(".,;:-–— ") + "."


def istraukti_vatikano_straipsni(url):
    """Atsisiunčia originalų, nepakeistą Vatican News straipsnio tekstą, pilną įvadą ir nuotrauką."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    soup = BeautifulSoup(html, "html.parser")

    # 1. Pagrindinė nuotrauka (og:image)
    img_url = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        img_url = og_img["content"].strip()
        if img_url.startswith("/"):
            img_url = "https://www.vaticannews.va" + img_url

    # 2. PILNA įžanga (pirmiausia imame iš HTML paantraštės bloko, kur ji NĖRA apkarpyta)
    pilnas_ivadas = ""
    lead_elem = soup.select_one(
        "div.article__subtitle, p.article__subtitle, h2.article__subtitle, .article__lead, .lead"
    )
    if lead_elem:
        pilnas_ivadas = lead_elem.get_text(" ", strip=True)

    if not pilnas_ivadas:
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            pilnas_ivadas = og_desc["content"].strip()

    # 3. Autentiškas straipsnio tekstas (be jokių nutraukimų)
    paragraphs = []
    content_blocks = soup.select("div.article__text, div.section--evidence .section__content")
    if not content_blocks:
        content_blocks = soup.select("article")

    for block in content_blocks:
        for unwanted in block.select(
            "script, style, .audio-player, .related-articles, figure, .article__subtitle, .article__lead"
        ):
            unwanted.decompose()

        for elem in block.find_all(["p", "h2", "h3", "blockquote"]):
            text_check = elem.get_text(" ", strip=True)
            if not text_check:
                continue
            if text_check.lower().startswith("taip pat skaitykite"):
                continue

            inner_html = "".join(str(child) for child in elem.contents).strip()
            paragraphs.append(f"<{elem.name}>{inner_html}</{elem.name}>")

        if paragraphs:
            break

    pilnas_html = "\n".join(paragraphs)
    return pilnas_html, pilnas_ivadas, img_url


def gauti_arba_sukurti_zyma(tag_name, headers):
    """Suranda esamą žymos ID pagal pavadinimą arba sukuria naują."""
    encoded_name = urllib.parse.quote(tag_name)
    url = f"https://www.bernardinai.lt/wp-json/wp/v2/tags?search={encoded_name}&per_page=30"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
            for t in tags:
                if t.get("name", "").strip().lower() == tag_name.strip().lower():
                    return int(t["id"])
    except Exception:
        pass

    try:
        create_url = "https://www.bernardinai.lt/wp-json/wp/v2/tags"
        payload = json.dumps({"name": tag_name}).encode("utf-8")
        h = headers.copy()
        h["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(create_url, data=payload, headers=h, method="POST")
        with urllib.request.urlopen(req) as resp:
            new_tag = json.loads(resp.read().decode("utf-8"))
            return int(new_tag["id"])
    except urllib.error.HTTPError as e:
        try:
            err_json = json.loads(e.read().decode("utf-8"))
            if err_json.get("code") == "term_exists":
                return int(err_json["data"]["term_id"])
        except Exception:
            pass
    except Exception:
        pass
    return None


def ikelti_nuotrauka_i_wp(img_url, wp_headers, idx):
    """Parsiunčia nuotrauką iš Vatican News ir įkelia į Bernardinai.lt Media biblioteką."""
    if not img_url or not img_url.startswith("http"):
        return None
    try:
        img_req = urllib.request.Request(
            img_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(img_req, timeout=20) as resp:
            img_data = resp.read()

        ext = ".jpg"
        mime_type = "image/jpeg"
        if ".png" in img_url.lower():
            ext = ".png"
            mime_type = "image/png"
        elif ".webp" in img_url.lower():
            ext = ".webp"
            mime_type = "image/webp"

        media_headers = wp_headers.copy()
        media_headers["Content-Type"] = mime_type
        media_headers["Content-Disposition"] = f'attachment; filename="vatican_news_{idx}{ext}"'

        req_media = urllib.request.Request(
            "https://www.bernardinai.lt/wp-json/wp/v2/media",
            data=img_data,
            headers=media_headers,
            method="POST",
        )
        with urllib.request.urlopen(req_media) as resp_media:
            media_json = json.loads(resp_media.read().decode("utf-8"))
            return int(media_json.get("id"))
    except Exception as e:
        print(f"Nepavyko įkelti nuotraukos ({img_url}): {e}")
        return None


def main():
    if not (WP_USER and WP_PASS):
        print("KLAIDA: Nėra WP_USERNAME arba WP_APP_PASSWORD aplinkos kintamųjų.")
        return

    auth_str = f"{WP_USER.strip()}:{WP_PASS.replace(' ', '').strip()}"
    basic_val = f"Basic {base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')}"
    wp_headers = {
        "Authorization": basic_val,
        "X-HTTP-Authorization": basic_val,
        "REDIRECT_HTTP_AUTHORIZATION": basic_val,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
        "X-Bnd-Automate": CF_KEY,
    }

    # Paruošiame standartines žymas
    tag_ids = []
    for zymos_pav in ["Vatican News", "Vatikanas"]:
        tid = gauti_arba_sukurti_zyma(zymos_pav, wp_headers)
        if tid:
            tag_ids.append(tid)

    publikuoti_url = uzkrauti_publikuotus()
    print("Tikrinamas Vatican News RSS srautas...")
    feed = feedparser.parse(VATICAN_RSS_URL)

    if not feed.entries:
        print("RSS srautas tuščias arba nepasiekiamas.")
        return

    naujausi_irasai = feed.entries[:MAX_FEED_ITEMS_TO_CHECK]
    laiko_riba = datetime.datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

    ikeltu_skaicius = 0
    for idx, entry in enumerate(reversed(naujausi_irasai)):
        if ikeltu_skaicius >= MAX_ARTICLES_PER_RUN:
            break

        link = getattr(entry, "link", "").strip()
        title = getattr(entry, "title", "").strip()
        rss_desc = getattr(entry, "description", "").strip()

        if not link or link in publikuoti_url:
            continue

        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_dt = datetime.datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if pub_dt < laiko_riba:
                print(f"Praleidžiamas senas straipsnis ({pub_dt.strftime('%Y-%m-%d %H:%M')}): {title}")
                continue

        print(f"\n>>> Ruošiamas straipsnis: {title}")
        try:
            pilnas_html, pilnas_ivadas, img_url = istraukti_vatikano_straipsni(link)

            if not pilnas_ivadas:
                pilnas_ivadas = re.sub(r"<[^>]+>", "", rss_desc).strip()

            if not pilnas_html or len(pilnas_html) < 100:
                pilnas_html = f"<p>{pilnas_ivadas}</p>"

            # 1. META APRAŠYMAS (ištraukai): iki 140 simbolių, baigtinis sakinys
            meta_aprasymas_140 = formuoti_meta_iki_140(
                pilnas_ivadas if pilnas_ivadas else pilnas_html
            )

            # 2. STRAIPSNIO TEKSTAS: įdedame 100% pilną įžangą be jokių nutraukimų
            svarus_tekstas_patikrai = re.sub(r"<[^>]+>", "", pilnas_html).strip()
            if pilnas_ivadas and pilnas_ivadas[:50] not in svarus_tekstas_patikrai:
                pilnas_html = f"<p><strong>{pilnas_ivadas}</strong></p>\n" + pilnas_html

            # PRIVALOMA DO-FOLLOW NUORODA IR ŠALTINIS PABAIGOJE
            saltinio_blokas = (
                f'\n<p><strong>Šaltinis: <a href="{link}">Vatican News</a></strong></p>'
            )
            galutinis_html = pilnas_html + saltinio_blokas

            # Įkeliame nuotrauką į WordPress
            featured_media_id = ikelti_nuotrauka_i_wp(img_url, wp_headers, idx)

            payload_wp = {
                "title": title,
                "content": galutinis_html,
                "excerpt": meta_aprasymas_140,                 # Standartinė WP ištrauka iki 140 simbolių
                "status": PUBLISH_STATUS,
                "categories": [WP_CATEGORY_ID],                # 24: Bažnyčia pasaulyje
                "tags": tag_ids,
                "meta": {
                    "_yoast_wpseo_metadesc": meta_aprasymas_140  # Yoast SEO meta aprašymas iki 140 simbolių
                },
                "acf": {
                    "short_description": meta_aprasymas_140,   # Trumpas aprašymas kortelėms (iki 140 simbolių, baigtinis sakinys)
                    "author": WP_ACF_AUTHOR_IDS,               # [858006, 8149]: Vatican News ir Bernardinai.lt
                    "source": [WP_ACF_SOURCE_ID],              # [59898]: Šaltinis „Vatican News“
                    "post_featured_image": "1",                # 1: Rodyti asociatyvią nuotrauką straipsnio viduje
                    "show_in_newest_posts": "yes",             # 13 laukas: yes : Rodyti Naujienose
                    "show_on_homepage": "no",                  # 12 laukas: no : Nerodyti „Redakcija rekomenduoja“
                },
            }

            if featured_media_id:
                payload_wp["featured_media"] = featured_media_id

            post_headers = wp_headers.copy()
            post_headers["Content-Type"] = "application/json; charset=utf-8"

            req_wp = urllib.request.Request(
                "https://www.bernardinai.lt/wp-json/wp/v2/posts",
                data=json.dumps(payload_wp).encode("utf-8"),
                headers=post_headers,
                method="POST",
            )

            with urllib.request.urlopen(req_wp) as resp_wp:
                wp_data = json.loads(resp_wp.read().decode("utf-8"))
                print(f">>> Sėkmingai publikuota: {wp_data.get('link')}")
                print(f"    Meta ištrauka ({len(meta_aprasymas_140)} simb.): {meta_aprasymas_140}")
                issaugoti_publikuota(link)
                ikeltu_skaicius += 1

        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            print(f">>> WordPress klaida ({e.code}) straipsniui '{title}': {err_msg}")
        except Exception as e:
            print(f">>> Klaida apdorojant '{title}': {e}")

    print(f"\nBaigta. Iš viso naujai įkelta straipsnių: {ikeltu_skaicius}")


if __name__ == "__main__":
    main()
