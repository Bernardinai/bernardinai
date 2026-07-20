import os
import re
import sys
import html
import time
import feedparser
import urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from moviepy.editor import VideoClip, ImageClip, CompositeVideoClip

# Nustatymai
RSS_URL = "https://www.bernardinai.lt/?feed=mailerlite"
TXT_FILE = "last_article.txt"
VIDEO_FILE = "bernardinai.mp4"
LOGO_FILE = "logo.png"
IMAGE_FILE = "article_image.jpg"

FONT_TITLE_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SUB_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def main():
    feedparser.USER_AGENT = "BernardinaiVideoBot/1.0"
    dynamic_url = f"{RSS_URL}&nocache={int(time.time())}"
    
    feed = feedparser.parse(dynamic_url)
    if not feed.entries:
        print("RSS srautas tuščias.")
        return

    latest_entry = feed.entries[0]
    latest_link = latest_entry.link
    latest_title = html.unescape(latest_entry.title)

    # Išlaikome inicialus ir dvigubas pavardes
    latest_title = latest_title.replace('. ', '.\u00A0')
    latest_title = latest_title.replace('-', '- ')

    old_link = ""
    if os.path.exists(TXT_FILE):
        with open(TXT_FILE, "r", encoding="utf-8") as f:
            old_link = f.read().strip()

    if latest_link == old_link:
        print("Naujų straipsnių nerasta. Agentas baigia darbą.")
        return

    print(f"Kuriame video: {latest_title}")

    image_url = None
    if 'media_content' in latest_entry and len(latest_entry.media_content) > 0:
        image_url = latest_entry.media_content[0].get('url')
    
    if not image_url:
        content_search = latest_entry.get('description', '')
        if 'content' in latest_entry:
            content_search += " " + str(latest_entry.content)
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_search, re.IGNORECASE)
        if img_match:
            image_url = img_match.group(1)

    if image_url:
        try:
            req = urllib.request.Request(image_url, headers={'User-Agent': 'BernardinaiVideoBot/1.0'})
            with urllib.request.urlopen(req) as response, open(IMAGE_FILE, 'wb') as out_file:
                out_file.write(response.read())
        except Exception as e:
            print(f"Nepavyko atsisiųsti nuotraukos: {e}")

    width, height = 1920, 1080
    
    # 1. UI SLUOKSNIS (Permatomas, statinis)
    ui_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    
    # Gradientas įskaitomumui
    start_fade = width // 3
    for x in range(width):
        if x > start_fade:
            opacity = min(240, int(240 * ((x - start_fade) / (width - start_fade))))
            draw.line([(x, 0), (x, height)], fill=(122, 34, 34, opacity))

    center_x = 1440
    max_text_width = 820

    # Logotipas
    logo_bottom_y = 100
    if os.path.exists(LOGO_FILE):
        try:
            logo = Image.open(LOGO_FILE).convert("RGBA")
            logo.thumbnail((500, 200)) 
            logo_x = center_x - (logo.width // 2)
            logo_y = 80
            
            padding_x = 30
            padding_y = 20
            bg_box = [logo_x - padding_x, logo_y - padding_y, logo_x + logo.width + padding_x, logo_y + logo.height + padding_y]
            draw.rounded_rectangle(bg_box, radius=15, fill=(255, 255, 255, 255))
            ui_canvas.paste(logo, (logo_x, logo_y), logo)
            
            logo_bottom_y = logo_y + logo.height + padding_y
        except:
            pass

    if not os.path.exists(FONT_TITLE_FILE):
        sys.exit(1)

    # CTA raginimas
    font_cta = ImageFont.truetype(FONT_TITLE_FILE, 35)
    cta_text = "SKAITYKITE BERNARDINAI.LT"
    cta_bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    cta_y = 1000
    
    cta_box = [center_x - cta_w//2 - 30, cta_y - 20, center_x + cta_w//2 + 30, cta_y + cta_h + 20]
    draw.rounded_rectangle(cta_box, radius=10, fill=(255, 255, 255, 255))
    draw.text((center_x, cta_y), cta_text, font=font_cta, fill=(122, 34, 34, 255), anchor="mt")

    # Teksto skaičiavimas ir išdėstymas
    available_height = cta_y - logo_bottom_y - 80 
    font_size = 90 
    lines = []
    
    while font_size > 20:
        font_title = ImageFont.truetype(FONT_TITLE_FILE, font_size)
        words = [w for w in latest_title.split(' ') if w]
        test_lines = []
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font_title)
            text_width = bbox[2] - bbox[0]
            
            if text_width < max_text_width:
                current_line = test_line
            else:
                if current_line: test_lines.append(current_line)
                current_line = word
        if current_line: test_lines.append(current_line)
        
        line_spacing = font_size * 1.3
        total_text_height = len(test_lines) * line_spacing
        
        if total_text_height <= available_height:
            lines = test_lines
            break 
            
        font_size -= 5 

    start_y = logo_bottom_y + 40 + (available_height - total_text_height) / 2
    
    # Pavadinimas su šešėliais
    for line in lines:
        draw.text((center_x + 4, start_y + 4), line, font=font_title, fill=(0, 0, 0, 200), anchor="ma")
        draw.text((center_x, start_y), line, font=font_title, fill=(255, 255, 255, 255), anchor="ma")
        start_y += line_spacing

    ui_path = "ui_layer.png"
    ui_canvas.save(ui_path)

    # 2. FONO SLUOKSNIS IR ANIMACIJA
    bg_clip = None
    if os.path.exists(IMAGE_FILE):
        try:
            article_img = Image.open(IMAGE_FILE).convert("RGB")
            article_img = ImageOps.fit(article_img, (width, height), method=Image.Resampling.LANCZOS)
            
            def make_zoom_frame(t):
                t_val = float(np.asarray(t).flatten()[0])
                
                zoom = 1 + 0.04 * t_val
                new_w = int(width * zoom)
                new_h = int(height * zoom)
                
                img_resized = article_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
                
                left = (new_w - width) // 2
                top = (new_h - height) // 2
                img_cropped = img_resized.crop((left, top, left + width, top + height))
                
                # Suliejimas pradedamas taikyti tik po 2 sekundžių (kad nebūtų per staigus perėjimas) ir padaromas švelnesnis.
                if t_val > 2:
                    blur_radius = float((t_val - 2) * 0.2) 
                    img_cropped = img_cropped.filter(ImageFilter.GaussianBlur(blur_radius))
                
                return np.array(img_cropped)

            bg_clip = VideoClip(make_zoom_frame, duration=10)
        except Exception as e:
            print(f"Klaida generuojant animaciją: {e}")
            pass
    
    if not bg_clip:
        fallback_bg = "fallback_bg.jpg"
        Image.new("RGB", (width, height), (122, 34, 34)).save(fallback_bg)
        bg_clip = ImageClip(fallback_bg).set_duration(10)

    # UI sluoksnio rodymas su uždelsimu: prasideda nuo 3 sekundės ir trunka likusias 7 sekundes, o paties išnirimo trukmė yra 1.5 sek.
    ui_clip = ImageClip(ui_path).set_start(3).set_duration(7).crossfadein(1.5)
    
    # 3. KOMPOZICIJA
    final_video = CompositeVideoClip([bg_clip, ui_clip], size=(width, height))
    final_video.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio=False)

    # Apsivalymas
    for temp_file in [ui_path, "fallback_bg.jpg", IMAGE_FILE]:
        if os.path.exists(temp_file): os.remove(temp_file)

    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_link)

if __name__ == "__main__":
    main()
