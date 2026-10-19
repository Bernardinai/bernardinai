import base64
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
MAX_ARTICLES_PER_RUN = 5  # Kiek daugiausia naujų straipsnių įkelti vieno paleidimo metu

# WordPress prisijungimai iš aplinkos kintamųjų (GitHub Secrets)
WP_USER = os.environ.get("WP_USERNAME", "")
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
CF_KEY = os.environ.get("CF_AUTOMATION_KEY", "")

# Tikslūs Bernardinai.lt ID pagal jūsų nustatymus
WP_CATEGORY_ID = 24            # Rubrika: „Bažnyčia pasaulyje“
WP_ACF_AUTHOR_ID = 858006      # Autorius: „Vatican News“
PUBLISH_STATUS = os.environ.get("WP_PUBLISH_STATUS", "publish")  # "publish" arba "draft"

feedparser.USER_AGENT = "Bernardinai-Vatican-Bot/1.0"


def uzkrauti_publikuotus():
    if not os.path.exists(TRACKER_FILE):
        return set()
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def issaugoti_publikuota(url):
    with open(TRACKER_FILE, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")


def sutrumpinti_iki_140(tekstas):
    """Sutrumpina ištrauką iki 140 simbolių neperpjaunant žodžio pusiau."""
    svarus = re.sub(r"<[^>]+>", "", tekstas).strip()
    svarus = re.sub(r"\s+", " ", svarus)
    if len(svarus) <= 140:
        return svarus
    apkarpytas = svarus[:137]
    if " " in apkarpytas:
        apkarpytas = apkarpytas.rsplit(" ", 1)[0]
    return apkarpytas + "..."


def istraukti_vatikano_straipsni(url):
    """Atsisiunčia originalų, nepakeistą Vatican News straipsnio tekstą, įvadą ir nuotrauką."""
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

    # 2. Įvadas / paantraštė (dažnai būna po antrašte arba meta description)
    ivadas = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        ivadas = og_desc["content"].strip()

    # 3. Autentiškas straipsnio tekstas (be jokių pakeitimų)
    paragraphs = []
    
    # Vatican News straipsnio teksto blokas
    content_blocks = soup.select("div.article__text, div.section--evidence .section__content")
    if not content_blocks:
        content_blocks = soup.select("article")

    for block in content_blocks:
        # Pašaliname vidinius audio grotuvus ar „Taip pat skaitykite“ blokus, jei tokių yra
        for unwanted in block.select("script, style, .audio-player, .related-articles, figure"):
            unwanted.decompose()

        for elem in block.find_all(["p", "h2", "h3", "blockquote"]):
            text_check = elem.get_text(strip=True)
            if not text_check:
                continue
            if text_check.lower().startswith("taip pat skaitykite"):
                continue

            inner_html = "".join(str(child) for child in elem.contents).strip()
            paragraphs.append(f"<{elem.name}>{inner_html}</{elem.name}>")

        if paragraphs:
            break

    pilnas_html = "\n".join(paragraphs)
    return pilnas_html, ivadas, img_url


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

    ikeltu_skaicius = 0
    # Einame nuo senesnių link naujesnių, kad išlaikytume chronologiją
    for idx, entry in enumerate(reversed(feed.entries)):
        if ikeltu_skaicius >= MAX_ARTICLES_PER_RUN:
            break

        link = getattr(entry, "link", "").strip()
        title = getattr(entry, "title", "").strip()
        rss_desc = getattr(entry, "description", "").strip()

        if not link or link in publikuoti_url:
            continue

        print(f"\n>>> Ruošiamas straipsnis: {title}")
        try:
            pilnas_html, ivadas, img_url = istraukti_vatikano_straipsni(link)

            if not pilnas_html or len(pilnas_html) < 100:
                pilnas_html = f"<p>{rss_desc}</p>"

            istraukos_saltinis = ivadas if ivadas else rss_desc
            if not istraukos_saltinis:
                istraukos_saltinis = pilnas_html
            trumpa_istrauka = sutrumpinti_iki_140(istraukos_saltinis)

            if ivadas and ivadas[:40] not in pilnas_html:
                pilnas_html = f"<p><strong>{ivadas}</strong></p>\n" + pilnas_html

            # PRIVALOMA DO-FOLLOW NUORODA IR ŠALTINIS PABAIGOJE (be jokių rel="nofollow")
            saltinio_blokas = (
                f'\n<p><strong>Šaltinis: <a href="{link}">Vatican News</a></strong></p>'
            )
            galutinis_html = pilnas_html + saltinio_blokas

            # Įkeliame nuotrauką į WordPress
            featured_media_id = ikelti_nuotrauka_i_wp(img_url, wp_headers, idx)

            payload_wp = {
                "title": title,
                "content": galutinis_html,
                "excerpt": trumpa_istrauka,
                "status": PUBLISH_STATUS,
                "categories": [WP_CATEGORY_ID],      # 24: Bažnyčia pasaulyje
                "tags": tag_ids,
                "acf": {
                    "short_description": trumpa_istrauka,
                    "author": [WP_ACF_AUTHOR_ID],    # 858006: Vatican News
                    "post_featured_image": "1",      # 1: Rodyti asociatyvią nuotrauką straipsnio viduje
                    "show_on_homepage": "no",        # Nerodyti „Redakcija rekomenduoja“
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
