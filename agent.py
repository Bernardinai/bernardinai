import os
import re
import sys
import html
import time
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

FONT_TITLE_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SUB_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def main():
    # 1. ANTI-CACHE GUDYRBĖ: Prisistatome kaip tikra naršyklė
    feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # 2. ANTI-CACHE GUDRYBĖ: Pridedame unikalų laiko kodą, kad gautume pačią naujausią RSS versiją
    dynamic_url = f"{RSS_URL}&nocache={int(time.time())}"
    
    feed = feedparser.parse(dynamic_url)
    if not feed.entries:
        print("RSS srautas tuščias.")
        return

    latest_entry = feed.entries[0]
    latest_link = latest_entry.link
    latest_title = html.unescape(latest_entry.title)

    old_link = ""
    if os.path.exists(TXT_FILE):
        with open(TXT_FILE, "r", encoding="utf-8") as f:
            old_link = f.read().strip()

    if latest_link == old_link:
        print("Naujų straipsnių nerasta. Agentas baigia darbą.")
        return

    print(f"Kuriame video: {latest_title}")

    # Nuotraukos paieška
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
            # Nuotraukos atsisiuntimui taip pat pridedame naršyklės antraštę
            req = urllib.request.Request(image_url, headers={'User-Agent': feedparser.USER_AGENT})
            with urllib.request.urlopen(req) as response, open(IMAGE_FILE, 'wb') as out_file:
                out_file.write(response.read())
        except Exception as e:
            print(f"Nepavyko atsisiųsti nuotraukos: {e}")

    # Ekrano paruošimas
    width, height = 1920, 1080
    bg_color = (122, 34, 34) 
    image_canvas = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(image_canvas)

    has_image = False
    if os.path.exists(IMAGE_FILE):
        try:
            article_img = Image.open(IMAGE_FILE).convert("RGB")
            article_img = ImageOps.fit(article_img, (960, 1080), method=Image.Resampling.LANCZOS)
            image_canvas.paste(article_img, (0, 0))
            has_image = True
        except:
            pass

    center_x = 1440 if has_image else 960
    max_text_width = 820 if has_image else 1700

    # Logotipo piešimas su baltu fonu
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
            draw.rounded_rectangle(bg_box, radius=15, fill=(255, 255, 255))
            image_canvas.paste(logo, (logo_x, logo_y), logo)
            
            logo_bottom_y = logo_y + logo.height + padding_y
        except:
            pass

    if not os.path.exists(FONT_TITLE_FILE):
        sys.exit(1)

    # Apatinio adreso piešimas
    font_sub_size = 40
    font_sub = ImageFont.truetype(FONT_SUB_FILE, font_sub_size)
    url_y = 1000
    draw.text((center_x, url_y), "www.bernardinai.lt", font=font_sub, fill=(255, 255, 255), anchor="mm")

    # Dinaminis šrifto dydžio skaičiavimas
    available_height = url_y - logo_bottom_y - 80 
    font_size = 90 
    lines = []
    
    while font_size > 20:
        font_title = ImageFont.truetype(FONT_TITLE_FILE, font_size)
        words = latest_title.split()
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
    
    for line in lines:
        draw.text((center_x, start_y), line, font=font_title, fill=(255, 255, 255), anchor="ma")
        start_y += line_spacing

    frame_path = "temp_frame.png"
    image_canvas.save(frame_path)

    clip = ImageClip(frame_path).set_duration(10)
    clip.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio=False)

    if os.path.exists(frame_path): os.remove(frame_path)
    if os.path.exists(IMAGE_FILE): os.remove(IMAGE_FILE)

    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write(latest_link)

if __name__ == "__main__":
    main()
