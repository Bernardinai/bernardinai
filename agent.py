import os
import feedparser
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip

# Nustatymai
RSS_URL = "https://www.bernardinai.lt/?feed=mailerlite"
TXT_FILE = "last_article.txt"
VIDEO_FILE = "bernardinai.mp4"
LOGO_FILE = "logo.png"
FONT_TITLE_FILE = "Roboto-Bold.ttf"
FONT_SUB_FILE = "Roboto-Regular.ttf"

def download_fonts():
    """Atsisiunčia šriftus, kad video tekstas atrodytų gražiai"""
    if not os.path.exists(FONT_TITLE_FILE):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf", FONT_TITLE_FILE)
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf", FONT_SUB_FILE)
            print("Šriftai sėkmingai atsisiųsti.")
        except Exception as e:
            print(f"Nepavyko atsisiųsti šriftų: {e}")

def main():
    # 1. Nuskaitome RSS srautą
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        print("RSS srautas tuščias arba nepasiekiamas.")
        return

    latest_entry = feed.entries[0]
    latest_link = latest_entry.link
    latest_title = latest_entry.title

    # 2. Patikriname, ar šis straipsnis jau buvo apdorotas
    old_link = ""
    if os.path.exists(TXT_FILE):
        with open(TXT_FILE, "r", encoding="utf-8") as f:
            old_link = f.read().strip()

    if latest_link == old_link:
        print("Naujų straipsnių nerasta. Agentas baigia darbą.")
        return

    print(f"Rastas naujas straipsnis: {latest_title}")
    download_fonts()

    # 3. Kadrų generavimas (Vaizdo kūrimas su Pillow)
    width, height = 1280, 720
    # Tradicinė Bernardinai.lt bordinė/ruda spalva (RGB: 122, 34, 34)
    bg_color = (122, 34, 34) 
    image = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(image)

    # Įkeliame logotipą, jei jis egzistuoja
    if os.path.exists(LOGO_FILE):
        try:
            logo = Image.open(LOGO_FILE).convert("RGBA")
            logo.thumbnail((400, 150))  # Proporcingai sumažiname logotipą
            logo_x = (width - logo.width) // 2
            logo_y = 60
            image.paste(logo, (logo_x, logo_y), logo)
        except Exception as e:
            print(f"Klaida įkeliant logotipą: {e}")

    # Šriftų paruošimas
    try:
        font_title = ImageFont.truetype(FONT_TITLE_FILE, 44)
        font_sub = ImageFont.truetype(FONT_SUB_FILE, 28)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Teksto skaldymas eilutėmis, kad netilpęs į vieną eilutę neišeitų iš ekrano kraštų
    words = latest_title.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        # Tikriname, ar eilutė neperžengia saugios ribos (1000 pikselių)
        if draw.textbbox((0, 0), test_line, font=font_title)[2] < 1000:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)

    # Užrašome straipsnio pavadinimą centre
    y_text = 320
    for line in lines:
        # Centruojame tekstą horizontaliai naudojant anchor="mm"
        draw.text((width // 2, y_text), line, font=font_title, fill=(255, 255, 255), anchor="mm")
        y_text += 60

    # Užrašome svetainės nuorodą apačioje
    draw.text((width // 2, height - 100), "www.bernardinai.lt", font=font_sub, fill=(240, 240, 240), anchor="mm")

    # Išsaugome laikiną nuotrauką
    frame_path = "temp_frame.png"
    image.save(frame_path)

    # 4. Video failo (.mp4) generavimas iš nuotraukos
    print("Generuojamas 10 sekundžių video failas...")
    clip = ImageClip(frame_path).set_duration(10)
    # Naudojame populiarų h264 kodeką, kad video grotų visuose įrenginiuose
    clip.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio=False)

    # Sutvarkome laikinus failus
    if os.path.exists(frame_path):
        os.remove(frame_path)

    # 5. Atnaujiname paskutinio straipsnio nuorodą faile, kad kitą kartą žinotume, jog šį jau padarėme
    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_link)

    print("Agentas sėkmingai sukūrė bernardinai.mp4 failą!")

if __name__ == "__main__":
    main()
