import whisper
import yt_dlp
import os
import sys
import traceback
from datetime import datetime

# --- НАСТРОЙКИ ---
# Путь к папке Obsidian (убедись, что он точный)
OBSIDIAN_PATH = r"C:\Users\bstn000000\Yandex.Disk\Obsidian Cloud\Clippings"

def sanitize_filename(filename):
    """Убирает запрещенные символы из имени файла"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename.strip()

def ensure_obsidian_folder():
    """Проверяет существование папки Obsidian и создает её при необходимости"""
    if not os.path.exists(OBSIDIAN_PATH):
        try:
            os.makedirs(OBSIDIAN_PATH)
            print(f"✅ Папка Obsidian создана: {OBSIDIAN_PATH}")
        except Exception as e:
            print(f"❌ Ошибка создания папки Obsidian: {e}")
            print("   Проверь путь и права доступа.")
            return False
    return True

def transcribe_youtube(url, model_size="base", language="Russian"):
    log_file = "error_log.txt"
    video_title = "Неизвестно"
    video_uploader = "Неизвестно"
    temp_filename = None
    final_audio_name = ""
    
    try:
        # Проверяем папку Obsidian сразу
        if not ensure_obsidian_folder():
            raise Exception("Недоступна папка Obsidian. Скрипт остановлен.")

        print(f"🎬 Анализ ссылки: {url}")
        
        # 1. Инфо о видео
        print("📺 Получаю информацию о видео...")
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl_info:
            try:
                info = ydl_info.extract_info(url, download=False)
                video_title = info.get('title', 'Без названия')
                video_uploader = info.get('uploader', 'Неизвестно')
                video_id = info.get('id', 'unknown')
                print(f"   Название: {video_title}")
                print(f"   Автор: {video_uploader}")
            except Exception as e:
                print(f"⚠️ Не удалось получить метаданные: {e}")
                video_title = "Unknown_Video"
                video_id = "unknown"

        safe_title = sanitize_filename(video_title)
        if len(safe_title) > 100:
            safe_title = safe_title[:100]
        
        # Имя для аудиофайла (сохраняем в папке со скриптом)
        final_audio_name = f"{safe_title}.mp3"

        # 2. Загрузка модели
        print(f"\n🤖 Загрузка модели Whisper ({model_size})...")
        model = whisper.load_model(model_size)

        # 3. Скачивание аудио
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'temp_audio_{video_id}.%(ext)s',
            'quiet': False,
        }

        print("\n⬇️ Скачивание аудио...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            base_name = f"temp_audio_{video_id}"
            possible_exts = ['.mp3', '.m4a', '.webm', '.wav', '.opus']
            found_file = None
            for ext in possible_exts:
                if os.path.exists(base_name + ext):
                    found_file = base_name + ext
                    break
            
            if not found_file:
                directory = os.path.dirname(base_name) or '.'
                prefix = os.path.basename(base_name)
                for file in os.listdir(directory):
                    if file.startswith(prefix) and any(file.endswith(e) for e in possible_exts):
                        found_file = os.path.join(directory, file)
                        break
            
            temp_filename = found_file

        if not temp_filename or not os.path.exists(temp_filename):
            raise FileNotFoundError("Аудиофайл не найден.")

        # 4. ТРАНСКРИБАЦИЯ С ЖИВЫМ ВЫВОДОМ
        print(f"\n🎤 НАЧИНАЮ ТРАНСКРИБАЦИЮ (текст появится ниже):")
        print("="*60)
        
        result = model.transcribe(temp_filename, language=language, verbose=True)
        transcript_text = result["text"]
        
        print("="*60)
        print("✅ Транскрибация завершена!")

        # 5. ПЕРЕИМЕНОВАНИЕ АУДИО (в папке со скриптом)
        print(f"\n💾 Сохраняю аудио как: {final_audio_name}")
        if os.path.exists(final_audio_name):
            base, ext = os.path.splitext(final_audio_name)
            counter = 1
            while os.path.exists(f"{base}_{counter}{ext}"):
                counter += 1
            final_audio_name = f"{base}_{counter}{ext}"
            print(f"   (Файл существовал, переименовано в {final_audio_name})")
        
        os.rename(temp_filename, final_audio_name)
        print(f"   ✅ Аудио сохранено локально: {final_audio_name}")

        # 6. СОЗДАНИЕ MARKDOWN ЗАМЕТКИ ДЛЯ OBSIDIAN
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_filename = f"{safe_title}.md"
        md_filepath = os.path.join(OBSIDIAN_PATH, md_filename)
        
        # Формируем содержимое .md файла
        # Ссылка на аудио будет относительной или абсолютной. 
        # Лучше использовать абсолютный путь к аудио, чтобы Obsidian точно его нашел,
        # или relative link, если аудио тоже лежит в Vault. 
        # Пока поставим абсолютный путь к аудиофайлу для надежности.
        abs_audio_path = os.path.abspath(final_audio_name).replace('\\', '/')
        
        markdown_content = f"""---
created: {timestamp}
tags:
  - youtube
  - транскрибация
  - clipping
source: "{url}"
author: "{video_uploader}"
---

# {video_title}

**Автор:** {video_uploader}  
**Дата обработки:** {timestamp}  
**Оригинал:** [Смотреть на YouTube]({url})  
**Аудио:** ![[{abs_audio_path}]] *(Если не воспроизводится, проверь путь)*

---

## 📝 Полная транскрибация

{transcript_text}

---
*Сгенерировано автоматически через Python-скрипт.*
"""
        
        # Записываем файл в папку Obsidian
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        print(f"\n🚀 ЗАМЕТКА СОЗДАНА В OBSIDIAN:")
        print(f"   Путь: {md_filepath}")
        print("   (Обнови Obsidian, если не видишь файл сразу)")

    except Exception as e:
        error_msg = f"\n❌ ПРОИЗОШЛА ОШИБКА:\n{str(e)}"
        print(error_msg)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now()}\n{error_msg}\n{traceback.format_exc()}")
        print(f"💾 Лог ошибки сохранен в: {log_file}")
        
    finally:
        print("\n" + "="*50)
        input(">>> НАЖМИ ENTER, ЧТОБЫ ЗАКРЫТЬ ОКНО <<<")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Вставь ссылку на YouTube видео: ")
    
    # Запуск с моделью base и русским языком
    transcribe_youtube(url, model_size="base", language="russian")