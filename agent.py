import os
import re
import html
import feedparser
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageOps
from moviepy.editor import ImageClip

# Nustatymai
RSS_URL = "https://www.bernardinai.lt/?feed=mailerlite"
TXT_FILE = "last_article.txt"
VIDEO_FILE = "bernardinai.mp4"
LOGO_FILE = "logo.png"
IMAGE_FILE = "article_image.jpg"
FONT_TITLE_FILE = "Roboto-Bold.ttf"
FONT_SUB_FILE = "Roboto-Regular.ttf"

def download_fonts():
    """Atsisiunčia šriftus"""
    if not os.path.exists(FONT_TITLE_FILE):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf", FONT_TITLE_FILE)
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf", FONT_SUB_FILE)
        except Exception as e:
            print(f"Nepavyko atsisiųsti šriftų: {e}")

def main():
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        print("RSS srautas tuščias arba nepasiekiamas.")
        return

    latest_entry = feed.entries[0]
    latest_link = latest_entry.link
    
    # Svarbu: iššifruojame HTML kodus į normalias lietuviškas raides!
    latest_title = html.unescape(latest_entry.title)

    # Patikriname, ar straipsnis naujas
    old_link = ""
    if os.path.exists(TXT_FILE):
        with open(TXT_FILE, "r", encoding="utf-8") as f:
            old_link = f.read().strip()

    if latest_link == old_link:
        print("Naujų straipsnių nerasta. Agentas baigia darbą.")
        return

    print(f"Kuriame video straipsniui: {latest_title}")
    download_fonts()

    # Nuotraukos paieška RSS viduje
    image_url = None
    
    # Bandoma rasti per media_content
    if 'media_content' in latest_entry and len(latest_entry.media_content) > 0:
        image_url = latest_entry.media_content[0].get('url')
    
    # Bandoma ištraukti per regex iš aprašymo turinio (HTML kodo)
    if not image_url:
        content_search = latest_entry.get('description', '')
        if 'content' in latest_entry:
            content_search += " " + str(latest_entry.content)
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_search, re.IGNORECASE)
        if img_match:
            image_url = img_match.group(1)

    # Nuotraukos atsisiuntimas
    if image_url:
        try:
            urllib.request.urlretrieve(image_url, IMAGE_FILE)
            print("Nuotrauka sėkmingai rasta ir atsisiųsta!")
        except Exception as e:
            print(f"Nepavyko atsisiųsti nuotraukos: {e}")

    # Full HD formatas ekranams
    width, height = 1920, 1080
    bg_color = (122, 34, 34) 
    image_canvas = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(image_canvas)

    has_image = False
    if os.path.exists(IMAGE_FILE):
        try:
            # Paimame nuotrauką ir pritaikome, kad užimtų lygiai pusę ekrano kairėje
            article_img = Image.open(IMAGE_FILE).convert("RGB")
            article_img = ImageOps.fit(article_img, (960, 1080), method=Image.Resampling.LANCZOS)
            image_canvas.paste(article_img, (0, 0))
            has_image = True
        except Exception as e:
            print(f"Klaida įkeliant nuotrauką į kadrą: {e}")

    # Nustatome teksto ir logotipo centrą (jei yra nuotrauka - dešinėje pusėje, jei ne - per vidurį)
    center_x = 1440 if has_image else 960
    max_text_width = 800 if has_image else 1600

    # Logotipas
    if os.path.exists(LOGO_FILE):
        try:
            logo = Image.open(LOGO_FILE).convert("RGBA")
            logo.thumbnail((500, 200))
            logo_x = center_x - (logo.width // 2)
            image_canvas.paste(logo, (logo_x, 80), logo)
        except:
            pass

    # Milžiniški šriftai
    font_title_size = 75
    font_sub_size = 45
    try:
        font_title = ImageFont.truetype(FONT_TITLE_FILE, font_title_size)
        font_sub = ImageFont.truetype(FONT_SUB_FILE, font_sub_size)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Teksto skaldymas į kelias eilutes
    words = latest_title.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if draw.textbbox((0, 0), test_line, font=font_title)[2] < max_text_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)

    # Dinamiškai apskaičiuojame nuo kurio aukščio pradėti rašyti, kad tekstas būtų centre
    total_text_height = len(lines) * (font_title_size + 20)
    y_text = (1080 - total_text_height) // 2 + 50 

    for line in lines:
        draw.text((center_x, y_text), line, font=font_title, fill=(255, 255, 255), anchor="mm")
        y_text += font_title_size + 20

    # Adresas pačioje apačioje
    draw.text((center_x, 1000), "www.bernardinai.lt", font=font_sub, fill=(240, 240, 240), anchor="mm")

    frame_path = "temp_frame.png"
    image_canvas.save(frame_path)

    print("Generuojamas Full HD video failas...")
    clip = ImageClip(frame_path).set_duration(10)
    clip.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio=False)

    if os.path.exists(frame_path): os.remove(frame_path)
    if os.path.exists(IMAGE_FILE): os.remove(IMAGE_FILE)

    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_link)

if __name__ == "__main__":
    main()
