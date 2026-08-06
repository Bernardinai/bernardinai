import os
import re
import sys
import html
import time
from datetime import datetime
import feedparser
import urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
from moviepy.editor import VideoClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
import moviepy.audio.fx.all as afx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- NUSTATYMAI ---
RSS_URL = "https://www.bernardinai.lt/?feed=mailerlite"
VIDEO_FILE = "bernardinai_dienos_apzvalga.mp4"
LOGO_FILE = "logo.png"
BG_MUSIC_FILE = "bg_music.mp3"
AI_LABEL_FILE = "LABEL_AI_black transparent 1.png"
MAX_ARTICLES = 4

FONT_TITLE_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SUB_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

import os
import time
import requests


def generate_audio(text, output_filename, title="Bernardinai Reels"):
    api_key = os.environ.get("MRFTB_API_KEY")
    if not api_key:
        print("!!! KLAIDA: Nerastas MRFTB_API_KEY aplinkos kintamasis.")
        return False

    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }

    # 1. Siunčiame užklausą su PRIVALOMAIS laukais (category_id)
    payload = {
        "title": title[:250],
        "content": text,
        "category_id": 9,  # Privalomas laukas pagal API dokumentaciją
        "type": "text",
        "status": "draft",
        "voice": "vytautas",  # Balsai: "astra", "laimis", "lina", "vytautas"
        "speed": 1.0,
        "audio": True,  # Aiškiai nurodome sugeneruoti garsą
    }

    try:
        print(
            f"Siunčiamas tekstas į MRFTB audio sintezę (balsas:"
            f" {payload['voice']})..."
        )
        response = requests.post(
            "http://www.mrftb.lt/api/articles",
            json=payload,
            headers=headers,
            timeout=30,
        )

        try:
            data = response.json()
        except Exception:
            print(
                f"!!! KLAIDA: Serveris grąžino ne JSON formatą: {response.text}"
            )
            return False

        # DIAGNOSTIKA: Atspausdiname tikslų atsakymą į logus
        print(f"API atsakymas: {data}")

        if not data.get("success"):
            print(
                f"!!! Nesėkmingas atsakymas iš API ({response.status_code}):"
                f" {data}"
            )
            return False

        article_data = data.get("data", {})
        article_id = article_data.get("id")

        if not article_id:
            print(
                "!!! KLAIDA: API atsakyme nėra straipsnio ID. Negalima"
                " patikrinti statuso."
            )
            return False

        # 2. PATIKRINIMO CIKLAS: laukiame iki 45 sek. (15 bandymų po 3 sek.)
        audio_url = article_data.get("audio") or data.get("synthesis", {}).get(
            "audio_url"
        )

        max_retries = 15
        retry_count = 0

        while not audio_url and retry_count < max_retries:
            retry_count += 1
            print(
                f"Audio dar generuojamas... Laukia ({retry_count}/{max_retries})"
                " - tikrinsime vėl po 3 sek."
            )
            time.sleep(3)

            get_resp = requests.get(
                f"http://www.mrftb.lt/api/articles/{article_id}",
                headers=headers,
                timeout=15,
            )
            if get_resp.status_code == 200:
                get_data = get_resp.json().get("data", {})
                audio_url = get_data.get("audio")
                if audio_url:
                    print(
                        f"Gautas audio URL po {retry_count} bandymų: {audio_url}"
                    )
                    break
            else:
                print(
                    f"Tikrinimo klaida ({get_resp.status_code}):"
                    f" {get_resp.text}"
                )

        if not audio_url:
            print(
                "!!! KLAIDA: Per skirtą laiką API nespėjo sugeneruoti audio"
                " nuorodos."
            )
            try:
                requests.delete(
                    f"http://www.mrftb.lt/api/articles/{article_id}",
                    headers=headers,
                    timeout=10,
                )
            except Exception:
                pass
            return False

        # 3. Atsisiunčiame paruoštą MP3 failą
        print(f"Atsisiunčiamas sugeneruotas audio failas iš: {audio_url}")
        audio_resp = requests.get(audio_url, timeout=30)
        if audio_resp.status_code == 200:
            with open(output_filename, "wb") as f:
                f.write(audio_resp.content)

            # 4. ŠVARA: ištriname laikiną juodraštį, kad neliktų priskirto fondams ar kategorijoms
            try:
                requests.delete(
                    f"http://www.mrftb.lt/api/articles/{article_id}",
                    headers=headers,
                    timeout=10,
                )
                print(
                    f"Laikinas juodraštis (ID: {article_id}) sėkmingai"
                    " ištrintas iš sistemos."
                )
            except Exception:
                pass

            return os.path.exists(output_filename)
        else:
            print(
                "!!! Nepavyko atsisiųsti audio failo"
                f" ({audio_resp.status_code})"
            )
            return False

    except Exception as e:
        print(f"!!! Klaida generuojant MRFTB garsą: {e}")
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

def upload_to_youtube(video_file, video_title, video_description):
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    
    if not (client_id and client_secret and refresh_token):
        print("!!! Nerasti YouTube prisijungimo raktai.")
        return
        
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token"
        )
        youtube = build("youtube", "v3", credentials=creds)
        
        body = {
            "snippet": {
                "title": video_title,
                "description": video_description,
                "tags": ["naujienos", "apžvalga", "bernardinai", "shorts", "lietuva", "katalikai"],
                "categoryId": "25" 
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }
        
        media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()
        print(f"Vaizdo įrašas sėkmingai įkeltas! YouTube ID: {response.get('id')}")
    except Exception as e:
        print(f"!!! Klaida įkeliant į YouTube: {e}")

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

    today_str = datetime.now().strftime("%Y-%m-%d")
    youtube_title = f"Bernardinai.lt dienos apžvalga ({today_str}) #Shorts"
    youtube_desc = "Svarbiausios dienos naujienos iš portalo Bernardinai.lt:\n\n"

    for index, entry in enumerate(articles_to_process):
        title = html.unescape(entry.title).replace('. ', '.\u00A0').replace('-', '- ')
        article_link = entry.get('link', 'https://www.bernardinai.lt')
        
        youtube_desc += f"• {title}\nSkaitykite: {article_link}\n\n"
        
        if index == 0:
            spoken_text = f"Šiandien Bernardinuose skaitykite: {title}."
            summary_text = "Šiandien Bernardinuose skaitykite:"
        elif index == len(articles_to_process) - 1:
            spoken_text = f"{title}. Tai ir dar daugiau rasite portale Bernardinai!"
            summary_text = "Tai ir dar daugiau rasite portale Bernardinai.lt!"
        else:
            spoken_text = f"{title}."
            summary_text = "Skaitykite portale Bernardinai.lt:"

        audio_file = f"temp_audio_{index}.mp3"
        has_audio = generate_audio(spoken_text, audio_file)

        if has_audio and os.path.exists(audio_file):
            audio_clip = AudioFileClip(audio_file)
            clip_duration = audio_clip.duration + 0.8 
        else:
            audio_clip = None
            clip_duration = 5.0

        image_url = None
        
        if 'media_content' in entry and len(entry.media_content) > 0:
            image_url = entry.media_content[0].get('url')
            
        if not image_url and 'links' in entry:
            for link in entry.links:
                if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                    image_url = link.get('href')
                    break
                    
        if not image_url:
            full_text = entry.get('description', '')
            if 'content' in entry:
                for c in entry.content:
                    full_text += " " + c.value
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', full_text, re.IGNORECASE)
            if img_match: 
                image_url = img_match.group(1)

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

        if os.path.exists(AI_LABEL_FILE):
            try:
                ai_label = Image.open(AI_LABEL_FILE).convert("RGBA")
                ai_label.thumbnail((120, 120)) 
                padding_x = 60
                padding_y = height - ai_label.height - 200 
                ui_canvas.paste(ai_label, (padding_x, padding_y), ai_label)
            except Exception as e:
                pass

        title_lines = wrap_text(title, font_title, max_text_width, draw)
        summary_lines = wrap_text(summary_text, font_summary, max_text_width, draw)

        title_spacing = 65 * 1.3
        summary_spacing = 42 * 1.4
        total_summary_h = len(summary_lines) * summary_spacing
        total_title_h = len(title_lines) * title_spacing
        
        start_y = (height // 2) - ((total_title_h + total_summary_h) // 2) + 50

        for line in summary_lines:
            draw.text((center_x + 3, start_y + 3), line, font=font_summary, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((center_x, start_y), line, font=font_summary, fill=(210, 210, 210, 255), anchor="ma")
            start_y += summary_spacing

        start_y += 30 
        
        for line in title_lines:
            draw.text((center_x + 4, start_y + 4), line, font=font_title, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((center_x, start_y), line, font=font_title, fill=(255, 255, 255, 255), anchor="ma")
            start_y += title_spacing
            
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

    youtube_desc += "\nŠiuos straipsnius (o ir kur kas daugiau) raskite atsivertę portalą Bernardinai.lt!\n"

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

    final_video.write_videofile(VIDEO_FILE, fps=24, codec="libx264", audio_codec="aac", preset="ultrafast", threads=2)

    for i in range(MAX_ARTICLES):
        for f in [f"temp_img_{i}.jpg", f"temp_ui_{i}.png", f"temp_bg_{i}.jpg", f"temp_audio_{i}.mp3"]:
            if os.path.exists(f): os.remove(f)
    if os.path.exists("temp_text.txt"):
        os.remove("temp_text.txt")

    print("Pradedamas vaizdo įrašo įkėlimas į YouTube...")
    upload_to_youtube(VIDEO_FILE, youtube_title, youtube_desc)

if __name__ == "__main__":
    main()
