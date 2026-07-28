import os
import re
import sys
import html
import time
import feedparser
import urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from moviepy.editor import VideoClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
import moviepy.audio.fx.all as afx
import google.generativeai as genai

# --- NUSTATYMAI ---
RSS_URL = "https://www.bernardinai.lt/?feed=mailerlite"
VIDEO_FILE = "bernardinai_dienos_apzvalga.mp4"
LOGO_FILE = "logo.png"
BG_MUSIC_FILE = "bg_music.mp3"
AI_LABEL_FILE = "LABEL_AI_black transparent 1.png" # Naujas nustatymas DI žymėjimui
MAX_ARTICLES = 4

FONT_TITLE_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SUB_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def generate_ai_sentence(title, full_text):
    if not GEMINI_KEY:
        return "Svarbus šiandienos tekstas."
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Tu esi Bernardinai.lt žurnalistas. Parašyk lygiai VIENO SAKINIO (apibendrinimo arba intriguojančio klausimo) "
            f"pristatymą šiam straipsniui. Maksimaliai 15 žodžių. Nenaudok kabučių. "
            f"Straipsnio antraštė: {title}. Tekstas: {full_text[:1000]}"
        )
        response = model.generate_content(prompt, safety_settings=[{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}, {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}, {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"}, {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}])
        res_text = response.text.strip().replace('\n', ' ')
        if not res_text.endswith(('.', '!', '?')):
            res_text += "."
        return res_text
    except Exception as e:
        print(f"!!! KLAIDA GENERUOJANT AI TEKSTĄ: {e}")
        return "Svarbus šiandienos tekstas."

def generate_audio(text, output_filename):
    try:
        with open("temp_text.txt", "w", encoding="utf-8") as f:
            f.write(text)
        os.system(f'edge-tts --voice lt-LT-OnaNeural -f temp_text.txt --write-media {output_filename}')
        return os.path.exists(output_filename)
    except:
        return False

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
        return

    articles_to_process = feed.entries[:MAX_ARTICLES]
    video_clips = []
    width, height = 1080, 1920
    center_x = width // 2
    max_text_width = 900 

    if not os.path.exists(FONT_TITLE_FILE):
        sys.exit(1)

    font_title = ImageFont.truetype(FONT_TITLE_FILE, 65)
    font_summary = ImageFont.truetype(FONT_SUB_FILE, 42)
    font_cta = ImageFont.truetype(FONT_TITLE_FILE, 35)

    for index, entry in enumerate(articles_to_process):
        title = html.unescape(entry.title).replace('. ', '.\u00A0').replace('-', '- ')
        full_text = entry.get('description', '') + " " + str(entry.get('content', ''))
        
        ai_sentence = generate_ai_sentence(title, full_text)
        summary_text = f"{ai_sentence} Išsamiau skaitykite portale Bernardinai.lt!"

        audio_file = f"temp_audio_{index}.mp3"
        spoken_text = f"{title}. {summary_text}"
        has_audio = generate_audio(spoken_text, audio_file)

        if has_audio and os.path.exists(audio_file):
            audio_clip = AudioFileClip(audio_file)
            clip_duration = audio_clip.duration + 0.8 
        else:
            audio_clip = None
            clip_duration = 7.0

        image_url = None
        if 'media_content' in entry and len(entry.media_content) > 0:
            image_url = entry.media_content[0].get('url')
        if not image_url:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', full_text, re.IGNORECASE)
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

        ui_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ui_canvas)
        
        if has_image:
            start_fade = height // 4
            for y in range(height):
                if y > start_fade:
                    opacity = min(245, int(245 * ((y - start_fade) / (height - start_fade))))
                    draw.line([(0, y), (width, y)], fill=(20, 20, 20, opacity))

        # 1. Pridedamas Logotipas
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
            except:
                pass

        # 2. Pridedamas DI žymėjimas (kairėje apačioje)
        if os.path.exists(AI_LABEL_FILE):
            try:
                ai_label = Image.open(AI_LABEL_FILE).convert("RGBA")
                ai_label.thumbnail((120, 120)) # Sumažiname, kad neatrodytų per didelis
                padding_x = 60
                padding_y = height - ai_label.height - 200 # Pakeliame virš socialinių tinklų aprašymų
                ui_canvas.paste(ai_label, (padding_x, padding_y), ai_label)
            except Exception as e:
                print(f"Nepavyko uždėti DI žymos: {e}")

        # Tekstų laužymas
        title_lines = wrap_text(title, font_title, max_text_width, draw)
        summary_lines = wrap_text(summary_text, font_summary, max_text_width, draw)

        title_spacing = 65 * 1.3
        summary_spacing = 42 * 1.4
        total_title_h = len(title_lines) * title_spacing
        
        start_y = (height // 2) - (total_title_h // 2) + 50

        for line in title_lines:
            draw.text((center_x + 4, start_y + 4), line, font=font_title, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((center_x, start_y), line, font=font_title, fill=(255, 255, 255, 255), anchor="ma")
            start_y += title_spacing
            
        start_y += 30 
        
        for line in summary_lines:
            draw.text((center_x + 3, start_y + 3), line, font=font_summary, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((center_x, start_y), line, font=font_summary, fill=(210, 210, 210, 255), anchor="ma")
            start_y += summary_spacing

        # Indikatorius apačioje centre
        counter_text = f"{index + 1} / {MAX_ARTICLES}"
        draw.rounded_rectangle([center_x - 60, height - 120, center_x + 60, height - 60], radius=8, fill=(122, 34, 34, 255))
        draw.text((center_x, height - 105), counter_text, font=font_cta, fill=(255, 255, 255, 255), anchor="mt")

        ui_path = f"temp_ui_{index}.png"
        ui_canvas.save(ui_path)

        bg_clip = None
        if has_image:
            try:
                article_img = Image.open(temp_img_file).convert("RGB")
                article_img = ImageOps.fit(article_img, (width, height), method=Image.Resampling.LANCZOS)
                
                def make_zoom_frame(t, img=article_img):
                    t_val = float(np.asarray(t).flatten()[0])
                    zoom = 1 + 0.03 * t_val
                    new_w = int(width * zoom)
                    new_h = int(height * zoom)
                    img_resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
                    left = (new_w - width) // 2
                    top = (new_h - height) // 2
                    img_cropped = img_resized.crop((left, top, left + width, top + height))
                    if t_val > 0.5:
                        blur_radius = float((t_val - 0.5) * 0.3) 
                        img_cropped = img_cropped.filter(ImageFilter.GaussianBlur(blur_radius))
                    return np.array(img_cropped)

                bg_clip = VideoClip(make_zoom_frame, duration=clip_duration)
            except Exception as e:
                pass

        if not bg_clip:
            fallback_bg = f"temp_bg_{index}.jpg"
            Image.new("RGB", (width, height), (60, 20, 20)).save(fallback_bg)
            bg_clip = ImageClip(fallback_bg).set_duration(clip_duration)

        ui_clip = ImageClip(ui_path).set_start(0).set_duration(clip_duration).crossfadein(0.4)
        
        final_clip = CompositeVideoClip([bg_clip, ui_clip], size=(width, height))
        if audio_clip:
            final_clip = final_clip.set_audio(audio_clip)

        video_clips.append(final_clip)

    final_video = concatenate_videoclips(video_clips, method="compose")

    if os.path.exists(BG_MUSIC_FILE):
        bg_audio = AudioFileClip(BG_MUSIC_FILE)
        bg_audio = afx.audio_loop(bg_audio, duration=final_video.duration)
        bg_audio = afx.volumex(bg_audio, 0.1)
        if final_video.audio:
            final_audio = CompositeAudioClip([final_video.audio, bg_audio])
            final_video = final_video.set_audio(final_audio)
        else:
            final_video = final_video.set_audio(bg_audio)

    final_video.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio_codec="aac")

    for i in range(MAX_ARTICLES):
        for f in [f"temp_img_{i}.jpg", f"temp_ui_{i}.png", f"temp_bg_{i}.jpg", f"temp_audio_{i}.mp3"]:
            if os.path.exists(f): os.remove(f)
    if os.path.exists("temp_text.txt"):
        os.remove("temp_text.txt")

if __name__ == "__main__":
    main()
