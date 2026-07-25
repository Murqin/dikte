"""Tiny translation helper.

Source strings are English; Turkish translations live in the TR table below.
No gettext, no .mo files; the string table is small enough to keep in code.
"""

import os

_lang = "en"


def resolve(code):
    """'auto' -> language guessed from the locale environment."""
    if code in ("tr", "en"):
        return code
    env = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
           or os.environ.get("LANG") or "")
    return "tr" if env.lower().startswith("tr") else "en"


def set_language(code):
    global _lang
    _lang = resolve(code)


def language():
    return _lang


def t(text, **kwargs):
    out = TR.get(text, text) if _lang == "tr" else text
    return out.format(**kwargs) if kwargs else out


TR = {
    # --- tray ---------------------------------------------------------
    "Start recording": "Kaydı başlat",
    "Stop and transcribe": "Kaydı bitir ve yaz",
    "Working…": "İşleniyor…",
    "Cancel recording": "Kaydı iptal et",
    "Settings…": "Ayarlar…",
    "Quit": "Çık",
    "Dikte: ready": "Dikte: hazır",
    "Dikte: recording": "Dikte: kaydediyor",
    "Dikte: working": "Dikte: işleniyor",

    # --- overlay / pipeline -------------------------------------------
    "Transcribing…": "Yazıya çevriliyor…",
    "Cleaning up…": "Temizleniyor…",
    "Pasting…": "Yapıştırılıyor…",
    "Pasted": "Yapıştırıldı",
    "Copied": "Panoya kopyalandı",
    "{action}: {preview}": "{action}: {preview}",
    "Cleanup skipped: {error}": "Temizleme atlandı: {error}",
    "No speech detected": "Ses algılanmadı",
    "No speech detected ({level} dB)": "Ses algılanmadı ({level} dB)",
    "Discarded a stock phrase: “{text}”": "Kalıp cümle atıldı: “{text}”",
    "Discard stock phrases models invent for near-silent audio":
        "Sessize yakın seste modelin uydurduğu kalıp cümleleri at",
    "Whisper answers silence with things like “Thanks for watching”.":
        "Whisper sessizliğe “Altyazı M.K.” gibi şeylerle karşılık verir.",
    "Speech also has to rise {margin} dB above the recording's own noise "
    "floor, so this absolute floor rarely needs touching. Lower it if quiet "
    "speech gets dropped; raise it if noise still gets through.":
        "Konuşmanın ayrıca kaydın kendi gürültü tabanının {margin} dB üstüne "
        "çıkması gerekir; bu mutlak taban nadiren değiştirilir. Kısık konuşma "
        "eleniyorsa düşür, gürültü hâlâ geçiyorsa yükselt.",
    "Recording too short, speak for at least 0.3 s": "Ses çok kısa, en az 0,3 saniye konuş",
    "Unexpected error: {error}": "Beklenmeyen hata: {error}",

    # --- audio / paste errors -----------------------------------------
    "pw-record not found. Is pipewire-audio installed?":
        "pw-record bulunamadı. pipewire-audio kurulu mu?",
    "Could not start recording: {error}": "Kayıt başlatılamadı: {error}",
    "wl-copy not found. Install wl-clipboard.":
        "wl-copy bulunamadı. wl-clipboard paketini kur.",
    "Could not copy to clipboard: {error}": "Panoya kopyalanamadı: {error}",
    "wl-copy exited with code {code}.": "wl-copy {code} koduyla çıktı.",
    "ydotool not found, cannot paste automatically.":
        "ydotool bulunamadı, otomatik yapıştırma yapılamıyor.",
    "Unknown key: {key}": "Bilinmeyen tuş: {key}",
    "Could not run ydotool: {error}": "ydotool çalıştırılamadı: {error}",
    "ydotool failed: {error}\nIs ydotoold running? (systemctl --user status ydotool)":
        "ydotool hatası: {error}\nydotoold çalışıyor mu? (systemctl --user status ydotool)",

    # --- api errors ----------------------------------------------------
    "OpenAI API key is empty. Add it in Settings.":
        "OpenAI API anahtarı boş. Ayarlar'dan gir.",
    "OpenRouter API key is empty. Add it in Settings.":
        "OpenRouter API anahtarı boş. Ayarlar'dan gir.",
    "Transcript came back empty.": "Transkript boş döndü.",
    "The cleanup model returned an empty reply.": "Temizleme modeli boş yanıt döndü.",
    "Could not connect: {reason}": "Bağlantı kurulamadı: {reason}",
    "Could not parse the response: {error}": "Yanıt çözümlenemedi: {error}",

    # --- settings: tabs and general ------------------------------------
    "Dikte Settings": "Dikte Ayarları",
    "General": "Genel",
    "API and models": "API ve modeller",
    "Cleanup rules": "Temizleme kuralları",
    "Audio file": "Ses dosyası",
    "Shortcut": "Kısayol",
    "History": "Geçmiş",
    "Save": "Kaydet",
    "Cancel": "Vazgeç",
    "Interface language": "Arayüz dili",
    "Automatic (system)": "Otomatik (sistem)",
    "Turkish": "Türkçe",
    "English": "İngilizce",
    "Restart Dikte for the language change to reach every window.":
        "Dil değişikliğinin her pencereye işlemesi için Dikte'yi yeniden başlat.",
    "Microphone": "Mikrofon",
    "Default microphone": "Varsayılan mikrofon",
    "Speech language": "Konuşma dili",
    "Detect automatically": "Otomatik algıla",
    "German": "Almanca",
    "French": "Fransızca",
    "Spanish": "İspanyolca",
    "Arabic": "Arapça",
    "Paste the text into the focused window": "Metni odaktaki pencereye yapıştır",
    "Paste key": "Yapıştırma tuşu",
    "Terminals usually want ctrl+shift+v. Change this if pasting does nothing.":
        "Terminaller genelde ctrl+shift+v ister. Yapıştırma çalışmıyorsa bunu değiştir.",
    "Restore the previous clipboard after pasting":
        "Yapıştırdıktan sonra eski pano içeriğini geri koy",
    "Indicator corner": "Gösterge köşesi",
    "bottom-left": "sol-alt",
    "bottom-right": "sağ-alt",
    "top-left": "sol-üst",
    "top-right": "sağ-üst",
    "Longest recording": "En uzun kayıt",
    " s": " sn",
    "Skip silent recordings (don't call the API)":
        "Sessiz kayıtları atla (API'ye gönderme)",
    "Silence threshold": "Sessizlik eşiği",
    "Keep audio files (~/.local/share/dikte/recordings)":
        "Ses kayıtlarını sakla (~/.local/share/dikte/recordings)",

    # --- settings: api --------------------------------------------------
    "OpenAI: speech to text": "OpenAI: sesi yazıya çevirme",
    "OpenRouter: transcript cleanup": "OpenRouter: transkripti temizleme",
    "API key": "API anahtarı",
    "Model": "Model",
    "sk-… (falls back to OPENAI_API_KEY)": "sk-… (boşsa OPENAI_API_KEY kullanılır)",
    "sk-or-… (falls back to OPENROUTER_API_KEY)": "sk-or-… (boşsa OPENROUTER_API_KEY kullanılır)",
    "Test key": "Anahtarı test et",
    "Trying…": "Deneniyor…",
    "Connection works. {count} audio models visible.":
        "Bağlantı tamam. {count} ses modeli görünüyor.",
    "Clean the transcript with a model": "Transkripti bir modelle temizle",
    "Fetch model list": "Model listesini çek",
    "Fetching model list…": "Model listesi çekiliyor…",
    "Could not fetch the list: {error}": "Liste alınamadı: {error}",
    "{count} models loaded.": "{count} model yüklendi.",

    # --- settings: prompt ------------------------------------------------
    "System instruction given to the cleanup model. This is where you decide "
    "how much it may touch your words.":
        "Temizleme modeline verilen sistem talimatı. Ne kadar müdahale edeceğini "
        "burada belirlersin.",
    "Reset to default": "Varsayılana döndür",
    "Transcription hint (optional): names and terms you say often. Helps "
    "Whisper spell them correctly.":
        "Transkripsiyon ipucu (isteğe bağlı): sık geçen özel isimler, terimler. "
        "Whisper'ın bunları doğru yazmasına yardım eder.",

    # --- settings: audio file --------------------------------------------
    "Transcribe an existing audio or video file with the same models.":
        "Var olan bir ses ya da video dosyasını aynı modellerle yazıya çevir.",
    "Choose file…": "Dosya seç…",
    "No file selected": "Dosya seçilmedi",
    "Select an audio file": "Bir ses dosyası seç",
    "Audio and video files": "Ses ve video dosyaları",
    "All files": "Tüm dosyalar",
    "Add timestamps": "Zaman damgası ekle",
    "Prefixes every segment with [mm:ss]. Uses whisper-1, the only model that "
    "returns segment times.":
        "Her bölümün başına [dd:ss] koyar. Bölüm zamanı döndüren tek model olan "
        "whisper-1 kullanılır.",
    "Run the cleanup model afterwards": "Sonrasında temizleme modelinden geçir",
    "Transcribe": "Yazıya çevir",
    "Stop": "Durdur",
    "Copy": "Panoya kopyala",
    "Save as .txt": "'.txt' olarak kaydet",
    "Save transcript": "Transkripti kaydet",
    "Text files": "Metin dosyaları",
    "Converting audio…": "Ses dönüştürülüyor…",
    "Splitting into {count} chunks…": "{count} parçaya bölünüyor…",
    "Transcribing chunk {index}/{count}…": "{index}/{count} parça yazıya çevriliyor…",
    "Done: {chars} characters.": "Bitti: {chars} karakter.",
    "Stopped.": "Durduruldu.",
    "Failed: {error}": "Başarısız: {error}",
    "ffmpeg not found. Install it to transcribe files.":
        "ffmpeg bulunamadı. Dosya çevirmek için kur.",
    "Could not read the file: {error}": "Dosya okunamadı: {error}",
    "Saved: {path}": "Kaydedildi: {path}",

    # --- settings: shortcut ------------------------------------------------
    "Install as a KDE shortcut": "KDE kısayolu olarak kur",
    "Remove": "Kaldır",
    "Registered in KDE: {shortcut}": "KDE'de kayıtlı: {shortcut}",
    "No KDE shortcut installed.": "KDE kısayolu kurulu değil.",
    "Use the built-in listener (/dev/input), for when the KDE shortcut is not active yet":
        "Yerleşik dinleyici kullan (/dev/input), KDE kısayolu henüz etkin değilken",
    "Works immediately, no session restart. The only difference: the key "
    "combination also reaches the focused application.":
        "Anında çalışır, oturum yenilemek gerekmez. Tek farkı: tuş kombinasyonu "
        "odaktaki uygulamaya da iletilir.",
    "KWin only reads shortcut settings at startup. After 'Install' the shortcut "
    "shows up under System Settings → Shortcuts, but it will not fire until you "
    "log out and back in. Until then, use the built-in listener.":
        "KWin, kısayol ayarlarını yalnızca açılışta okur. 'Kur' dedikten sonra kısayol "
        "Sistem Ayarları → Kısayollar altında görünür ama oturumu yeniden açana kadar "
        "tetiklenmez. O zamana kadar yerleşik dinleyiciyi kullanabilirsin.",
    "Shortcut conflict": "Kısayol çakışması",
    "{shortcut} is also used by:\n\n{list}\n\nInstall anyway?":
        "{shortcut} şu girdilerde de kullanılıyor:\n\n{list}\n\nYine de kurulsun mu?",
    "Shortcut saved: {shortcut}\nKWin only reads this file at startup, so it "
    "will not fire until you log out and back in. To use it right away, turn on "
    "the built-in listener.":
        "Kısayol kaydedildi: {shortcut}\nKWin bu dosyayı yalnızca açılışta okuduğu için "
        "oturumu yeniden açana kadar tetiklenmez. Hemen kullanmak istersen "
        "yerleşik dinleyiciyi aç.",
    "Could not write the desktop file: {error}": "Desktop dosyası yazılamadı: {error}",
    "Could not write kglobalshortcutsrc: {error}": "kglobalshortcutsrc yazılamadı: {error}",
    "Could not parse the shortcut: {shortcut}": "Kısayol çözümlenemedi: {shortcut}",
    "Cannot read /dev/input. Your user needs to be in the 'input' group:\n"
    "  sudo usermod -aG input $USER   (then log out and back in)":
        "/dev/input okunamıyor. Kullanıcının 'input' grubunda olması gerekir:\n"
        "  sudo usermod -aG input $USER   (sonra oturumu yeniden aç)",

    # --- settings: history --------------------------------------------------
    "Copy selected to clipboard": "Seçiliyi panoya kopyala",
    "Reload": "Yenile",
    "{ts}  ({duration} s)": "{ts}  ({duration} sn)",
}
