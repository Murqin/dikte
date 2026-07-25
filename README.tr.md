# Dikte

`Ctrl+Space`'e bas, konuş, tekrar bas. Ses OpenAI'ye gidip yazıya çevrilir,
OpenRouter'daki bir model transkripti temizler (ıı'lar, tekrarlar, eksik
noktalama), sonuç panoya kopyalanır ve o an yazdığın pencereye yapıştırılır.

KDE Plasma 6 / Wayland için yazıldı. Sistem paketleri dışında bağımlılığı yok:
sadece Python standart kütüphanesi ve PyQt6.

*[English README](README.md)*

<p align="center">
  <img src="docs/settings-general.webp" width="820" alt="Dikte ayarları, Genel sekmesi">
</p>

|  |  |
|---|---|
| <img src="docs/settings-api.webp" width="410" alt="API ve modeller"> | <img src="docs/settings-cleanup.webp" width="410" alt="Temizleme kuralları"> |
| <img src="docs/settings-audio-file.webp" width="410" alt="Ses dosyası"> | <img src="docs/settings-history.webp" width="410" alt="Geçmiş"> |

## Kurulum

```sh
./install.sh                 # ya da:  ./install.sh "Ctrl+Alt+Space"
dikte                        # ilk açılışta ayarlar penceresi gelir
```

Gereken sistem paketleri (Arch/CachyOS):

```sh
sudo pacman -S --needed pipewire-audio wl-clipboard ydotool ffmpeg python-pyqt6
systemctl --user enable --now ydotool     # otomatik yapıştırma için
```

Ayarlar penceresinde iki anahtar istenir:

- **OpenAI**: sesi yazıya çevirir (`gpt-4o-transcribe`). Boş bırakırsan
  `OPENAI_API_KEY` ortam değişkeni kullanılır.
- **OpenRouter**: transkripti temizler (varsayılan
  `google/gemini-3.5-flash-lite`, listedeki her model çalışır). Boşsa
  `OPENROUTER_API_KEY` kullanılır. Temizlemeyi tamamen kapatabilirsin; o zaman
  ham transkript yapıştırılır.

## Kullanım

| Ne | Nasıl |
| --- | --- |
| Kaydı başlat / bitir | `Ctrl+Space`, ya da tepsi simgesine tıkla |
| Kaydı iptal et | Tepsi menüsü → *Kaydı iptal et*, ya da `dikte cancel` |
| Ayarlar | Tepsi menüsü → *Ayarlar*, ya da `dikte settings` |
| Güncelleme sonrası yeniden yükle | Tepsi menüsü → *Yeniden başlat*, ya da `dikte restart` |
| Çık | Tepsi menüsü → *Çık*, ya da `dikte quit` |

Kayıt sırasında ekranın sol alt köşesinde küçük bir gösterge belirir: kırmızı
kayıt noktası, canlı ses dalgası, süre. Ardından "Yazıya çevriliyor…",
"Temizleniyor…" ve son olarak yapıştırılan metnin ilk satırı görünür. Gösterge
odak almaz, yani yazdığın pencereden çıkmazsın.

## Sessizlik API'ye gitmez

Sessize yakın bir ses verildiğinde transkripsiyon modeli boş dize döndürmez,
bir cümle uydurur. Whisper bunun ünlü örneği: iki saniyelik sessizliğe
"Altyazı M.K." ya da "Thanks for watching" der. Yanlışlıkla basılan bir
`Ctrl+Space` yoksa sana hem bir API çağrısına mal olur hem de hiç söylemediğin
bir cümleyi yapıştırır.

Dikte çağrıyı harcamadan önce kontrol eder ve bu kontrol mutlak değil göreli
yapılır, çünkü mikrofon kazancı makineden makineye o kadar değişir ki sabit bir
eşik bir şey ifade etmez. Şunlardan biri bile geçerliyse kayıt atılır:

- kaydın gürültülü ucu mutlak tabanın altındaysa (varsayılan -55 dBFS);
- **o kaydın kendi** gürültü tabanının 10 dB üstüne en az 0,3 saniye çıkan bir
  şey yoksa; ne kadar yüksek olursa olsun sabit fan ya da cızırtıyı eleyen de
  budur;
- seviye taban civarında hiç hareket etmediyse.

Yine de bir şey sızarsa, ikinci bir filtre modellerin sığındığı kalıp cümleleri
yakalar; ama yalnızca altı saniyeden kısa kayıtlarda, ki gerçekten söylenmiş
bir "izlediğiniz için teşekkürler" elenmesin.

Gösterge ölçtüğü seviyeyi de yazar (`Ses algılanmadı (-56 dB)`); mikrofonun
alışılmadık ölçüde kısık ya da gürültülüyse eşiği buna bakarak ayarlarsın.

## Yanlış duyulan kelimeleri düzeltme

Konuşma modelleri özel isimleri katlediyor. Ürün adları, teknik terimler ve
kısaltmalar sesçe benzeyen ama anlamsız bir şeye dönüşüyor; kelimenin kendisi
yanlışsa noktalama düzeltmenin bir faydası olmuyor. Temizleme modelinden bunları
bağlamdan onarması isteniyor, bağlam hangi kelime olduğunu netleştirmiyorsa da
dokunmaması söyleniyor; yani tahmin etmiyor, düzeltiyor.

Temizleme kuralları sekmesine girdiğin isim listesi burada iki iş görüyor:
transkripsiyon modeline ipucu, temizleme modeline sözlük olarak gidiyor. İkinci
modelin bozuk bir transkriptte o ismi tanıyabilmesi, doğru yazımını bilmesine
bağlı. Kutuya `Kubernetes, Grafana, PyQt` yazıldığında:

```
ham    ıı bugün şey kuber netis üzerinde çalışan servisleri güncelledim
       yani sonra grafanada bir panel açtım hani ve pay kut ile arayüzü
       şey bitirdim işte

sonuç  Bugün Kubernetes üzerinde çalışan servisleri güncelledim. Sonra
       Grafana'da bir panel açtım ve PyQt ile arayüzü bitirdim.
```

Temizlemenin kendisi başarısız olursa, reddedilen bir anahtar ya da boşalmış bir
hesap yüzünden, dikte kaybolmasın diye ham transkript yine yapıştırılır; ama
gösterge kehribar rengine döner ve neyin ters gittiğini söyler, tam gerekçe de
bildirimde yazar. Temizlenmemiş bir metni model çalışmış gibi sessizce eline
tutuşturmaz.

## Dosyadan transkript

Ayarlar → **Ses dosyası** sekmesi, herhangi bir ses ya da video dosyasını aynı
modellerden geçirir. İki seçenek var, ikisi de hatırlanır:

- **Zaman damgası ekle**: her bölümün başına `[dd:ss]` koyar. Bunun için bölüm
  zamanı döndüren tek model olan `whisper-1` kullanılır.
- **Sonrasında temizleme modelinden geçir**: canlı diktedeki temizlemenin
  aynısı, üstüne modele damgalara dokunmamasını söyleyen bir kural eklenir.

Uzun dosyalar ffmpeg ile 16 kHz mono'ya çevrilip onar dakikalık parçalara
bölünür; her parça sırayla çevrilir ve zaman damgaları kendi yerine kaydırılır.
Sonuç panoya kopyalanabilir ya da `.txt` olarak kaydedilebilir.

## Global kısayol hakkında

KWin, `kglobalshortcutsrc` dosyasını yalnızca açılışta okur. `install.sh`
kısayolu doğru yere yazar ama **oturumu yeniden açana kadar tetiklenmez.**
İki seçenek:

1. Oturumu kapat-aç. Temiz çözüm bu: tuşu KWin yuttuğu için diğer uygulamalara
   sızmaz.
2. Ayarlar → Kısayol → **Yerleşik dinleyici**'yi aç. `/dev/input` üzerinden
   kombinasyonu kendisi yakalar, anında çalışır. Tek farkı: tuşu yutmaz, yani
   `Ctrl+Space` odaktaki uygulamaya da iletilir (bazı editörlerde otomatik
   tamamlama açılabilir). Rahatsız ederse kısayolu `Ctrl+Alt+Space` gibi bir
   kombinasyona çevir.

Yerleşik dinleyici `input` grubunda olmayı gerektirir:
`sudo usermod -aG input $USER`.

## Ayarlar

`~/.config/dikte/config.json` içinde, izinler 600, çünkü API anahtarları orada durur.

| Ayar | Açıklama |
| --- | --- |
| Arayüz dili | Türkçe, İngilizce ya da sistem diline uy |
| Mikrofon | Belirli bir kaynak seç, ya da varsayılanı kullan |
| Konuşma dili | Transkripsiyona dil ipucu verir; otomatik algılama da olur |
| Yapıştırma tuşu | `ctrl+v` / `ctrl+shift+v` / `shift+insert`. Terminaller genelde ikincisini ister |
| Panoyu geri koy | Yapıştırdıktan sonra eski pano içeriğini iade eder |
| Sessiz kayıtları atla | Konuşma içermeyen kayıtları API'ye gitmeden eler, yukarıya bak |
| Temizleme kuralları | Temizleme modeline verilen sistem talimatı. Ne kadar müdahale edeceğini burada belirlersin |
| İsimler ve terimler | Transkripsiyon modeline ipucu, temizleme modeline sözlük; özel isimlerin doğru yazılması için |
| Ses kayıtlarını sakla | WAV'lar `~/.local/share/dikte/recordings` altında kalır |

Geçmiş `~/.local/share/dikte/history.jsonl` dosyasında tutulur; son 200 kayıt
Ayarlar → Geçmiş sekmesinden görülebilir.

## Dosyalar

```
dikte.py          giriş noktası, tepsi simgesi, durum makinesi, IPC
audio.py          pw-record ile ham PCM kaydı ve seviye ölçer
api.py            OpenAI transkript + OpenRouter temizleme (yalnız stdlib)
worker.py         transkript → temizleme → pano → yapıştırma
vad.py            kayıtta gerçekten konuşma var mı kararı
filetranscribe.py dosyadan transkript: ffmpeg, parçalama, zaman damgaları
overlay.py        köşedeki gösterge
settings_ui.py    ayarlar penceresi
hotkey.py         KDE kısayol kurulumu ve evdev dinleyici
paste.py          wl-clipboard ve ydotool sarmalayıcıları
i18n.py           metin tablosu
```

## Bilinen sınırlar

- Gösterge XWayland üzerinden çizilir; Wayland'da bir pencereyi belirli bir
  köşeye yerleştirmenin yolu yok. `dikte.py` bu yüzden `QT_QPA_PLATFORM=xcb`
  ayarlar.
- Otomatik yapıştırma `ydotool`'un sanal klavyesiyle yapılır; `ydotoold`
  çalışmıyorsa metin yalnızca panoya kopyalanır ve gösterge bunu söyler.
- "Yazıya çevriliyor…" sürerken gelen kısayol basışları yok sayılır.

## Lisans

GPL-3.0, [LICENSE](LICENSE) dosyasına bak.
