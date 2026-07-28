import os
import re
import sys
import html
import time
import feedparser
import urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from moviepy.editor import VideoClip, ImageClip, CompositeVideoClip, concatenate_videoclips

# --- NUSTATYMAI ---
RSS_URL = "https://www.bernardinai.lt/?feed=mailerlite"
VIDEO_FILE = "bernardinai_dienos_apzvalga.mp4"
LOGO_FILE = "logo.png"
MAX_ARTICLES = 4
CLIP_DURATION = 10 # Kiekvieno straipsnio rodymo trukmė sekundėmis

FONT_TITLE_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SUB_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Pagalbinė funkcija teksto laužymui
def wrap_text(text, font, max_width, draw):
    words = [w for w in text.split(' ') if w]
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) < max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)
    return lines

def main():
    feedparser.USER_AGENT = "BernardinaiVideoBot/1.0"
    dynamic_url = f"{RSS_URL}&nocache={int(time.time())}"
    feed = feedparser.parse(dynamic_url)
    
    if not feed.entries:
        print("RSS srautas tuščias.")
        return

    # Paimame 4 naujausius straipsnius
    articles_to_process = feed.entries[:MAX_ARTICLES]
    print(f"Rasta straipsnių: {len(articles_to_process)}. Pradedamas video generavimas...")

    video_clips = []
    width, height = 1080, 1920
    center_x = width // 2
    max_text_width = 900 

    if not os.path.exists(FONT_TITLE_FILE):
        print("Nerastas šriftas!")
        sys.exit(1)

    font_title = ImageFont.truetype(FONT_TITLE_FILE, 70)
    font_summary = ImageFont.truetype(FONT_SUB_FILE, 45)
    font_cta = ImageFont.truetype(FONT_TITLE_FILE, 35)

    for index, entry in enumerate(articles_to_process):
        title = html.unescape(entry.title).replace('. ', '.\u00A0').replace('-', '- ')
        print(f"Apdorojamas [{index + 1}/{len(articles_to_process)}]: {title}")

        # TODO 1: AI Teksto sutrumpinimas
        # Čia vėliau jungsis OpenAI API, kuri paims entry.description ir pavers jį 2 sakinių intriga.
        # Kol kas naudojame simuliaciją:
        summary_text = "Vienas svarbiausių šios dienos tekstų, kurį privalote perskaityti. Sužinokite visas detales portale."

        # TODO 2: Audio generavimas (TTS)
        # Čia vėliau jungsis ElevenLabs arba OpenAI TTS, kuris perskaitys 'title' ir 'summary_text'.
        # Sugeneruotas garso failas bus priskiriamas prie sukurto video klipo.

        # Ieškome nuotraukos
        image_url = None
        if 'media_content' in entry and len(entry.media_content) > 0:
            image_url = entry.media_content[0].get('url')
        if not image_url:
            content_search = entry.get('description', '') + " " + str(entry.get('content', ''))
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_search, re.IGNORECASE)
            if img_match: image_url = img_match.group(1)

        temp_img_file = f"temp_img_{index}.jpg"
        has_image = False
        if image_url:
            try:
                req = urllib.request.Request(image_url, headers={'User-Agent': 'BernardinaiVideoBot/1.0'})
                with urllib.request.urlopen(req) as response, open(temp_img_file, 'wb') as out_file:
                    out_file.write(response.read())
                Image.open(temp_img_file).verify()
                has_image = True
            except:
                has_image = False

        # --- UI SLUOKSNIS ---
        ui_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ui_canvas)
        
        # Tamsus gradientas įskaitomumui
        if has_image:
            start_fade = height // 4
            for y in range(height):
                if y > start_fade:
                    opacity = min(245, int(245 * ((y - start_fade) / (height - start_fade))))
                    draw.line([(0, y), (width, y)], fill=(20, 20, 20, opacity))

        # Logotipas
        logo_bottom_y = 150
        if os.path.exists(LOGO_FILE):
            try:
                logo = Image.open(LOGO_FILE).convert("RGBA")
                logo.thumbnail((350, 150)) 
                logo_x = center_x - (logo.width // 2)
                logo_y = 120
                padding = 20
                bg_box = [logo_x - padding, logo_y - padding, logo_x + logo.width + padding, logo_y + logo.height + padding]
                draw.rounded_rectangle(bg_box, radius=12, fill=(255, 255, 255, 255))
                ui_canvas.paste(logo, (logo_x, logo_y), logo)
                logo_bottom_y = logo_y + logo.height + padding
            except:
                pass

        # Tekstų laužymas
        title_lines = wrap_text(title, font_title, max_text_width, draw)
        summary_lines = wrap_text(summary_text, font_summary, max_text_width, draw)

        # Skaičiuojame aukščius
        title_spacing = 70 * 1.3
        summary_spacing = 45 * 1.4
        total_title_h = len(title_lines) * title_spacing
        total_summary_h = len(summary_lines) * summary_spacing
        
        # Išdėstome tekstą ekrano centre/apačioje
        start_y = (height // 2) - (total_title_h // 2) + 100

        # Piešiame Pavadinimą
        for line in title_lines:
            draw.text((center_x + 4, start_y + 4), line, font=font_title, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((center_x, start_y), line, font=font_title, fill=(255, 255, 255, 255), anchor="ma")
            start_y += title_spacing
            
        start_y += 40 # Tarpas tarp antraštės ir santraukos
        
        # Piešiame Santrauką
        for line in summary_lines:
            draw.text((center_x + 3, start_y + 3), line, font=font_summary, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((center_x, start_y), line, font=font_summary, fill=(200, 200, 200, 255), anchor="ma")
            start_y += summary_spacing

        # Numeracijos indikatorius (pvz., "1 iš 4")
        counter_text = f"{index + 1} / {MAX_ARTICLES}"
        draw.rounded_rectangle([center_x - 60, height - 120, center_x + 60, height - 60], radius=8, fill=(122, 34, 34, 255))
        draw.text((center_x, height - 105), counter_text, font=font_cta, fill=(255, 255, 255, 255), anchor="mt")

        ui_path = f"temp_ui_{index}.png"
        ui_canvas.save(ui_path)

        # --- FONO ANIMACIJA ---
        bg_clip = None
        if has_image:
            try:
                article_img = Image.open(temp_img_file).convert("RGB")
                article_img = ImageOps.fit(article_img, (width, height), method=Image.Resampling.LANCZOS)
                
                def make_zoom_frame(t, img=article_img):
                    t_val = float(np.asarray(t).flatten()[0])
                    zoom = 1 + 0.04 * t_val
                    new_w = int(width * zoom)
                    new_h = int(height * zoom)
                    img_resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
                    
                    left = (new_w - width) // 2
                    top = (new_h - height) // 2
                    img_cropped = img_resized.crop((left, top, left + width, top + height))
                    
                    if t_val > 0.5:
                        blur_radius = float((t_val - 0.5) * 0.4) 
                        img_cropped = img_cropped.filter(ImageFilter.GaussianBlur(blur_radius))
                    
                    return np.array(img_cropped)

                bg_clip = VideoClip(make_zoom_frame, duration=CLIP_DURATION)
            except Exception as e:
                print(f"Klaida su nuotrauka {index}: {e}")
                pass
        
        if not bg_clip:
            fallback_bg = f"temp_bg_{index}.jpg"
            Image.new("RGB", (width, height), (60, 20, 20)).save(fallback_bg)
            bg_clip = ImageClip(fallback_bg).set_duration(CLIP_DURATION)

        # Sujungiame foną ir UI. UI atsiranda iškart.
        ui_clip = ImageClip(ui_path).set_start(0).set_duration(CLIP_DURATION).crossfadein(0.5)
        final_clip = CompositeVideoClip([bg_clip, ui_clip], size=(width, height))
        
        video_clips.append(final_clip)

    # --- 4. KLIPŲ SUJUNGIMAS Į VIENĄ VIDEO ---
    print("Sujungiami visi klipai į vieną vaizdo įrašą...")
    # 'compose' metodas užtikrina sklandų sujungimą be klaidų
    final_video = concatenate_videoclips(video_clips, method="compose")
    
    # Išsaugome galutinį rezultatą
    final_video.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio=False)

    # --- 5. APSIVALYMAS ---
    print("Valomi laikini failai...")
    for i in range(MAX_ARTICLES):
        for prefix in ["temp_img_", "temp_ui_", "temp_bg_"]:
            tmp_file = f"{prefix}{i}.jpg" if "bg" in prefix or "img" in prefix else f"{prefix}{i}.png"
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    print(f"SĖKMĖ! Vaizdo įrašas išsaugotas kaip: {VIDEO_FILE}")
    # TODO 3: YouTube Data API įkėlimas
    # Čia bus funkcija upload_to_youtube(VIDEO_FILE, title="Šiandien Bernardinai.lt", tags=...)

if __name__ == "__main__":
    main()
