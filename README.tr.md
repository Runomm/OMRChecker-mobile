# OMRChecker Mobile

[English](README.md)

[Udayraj123/OMRChecker](https://github.com/Udayraj123/OMRChecker) projesinin bir fork'u; üstüne bir telefon uygulaması ve küçük bir masaüstü paneli ekledim. Kullanım senaryosu basit: öğretmen optik formların fotoğrafını telefonla çekiyor, notlar bilgisayardaki Excel sınıf listesine yazılıyor.

Kabarcık okuma işini OMRChecker'ın kendisi yapıyor. Bu fork'un eklediği kısımlar:

- `omr_scanner_app/`: Android için Flutter uygulaması. Bilgisayarda görünen QR kodu okutuyorsun, formun fotoğrafını çekip kırpıyorsun ve gönderiyorsun. Uygulama öğrenci numarasını ve notu gösteriyor.
- `gui.py`: masaüstü kontrol paneli (CustomTkinter). Sunucuyu başlatıyor, bilgisayarın yerel IP'sini ve uygulama için QR kodu gösteriyor, sınıf listesiyle cevap anahtarını yüklüyor ve `inputs/` içindeki görsellerle elle test yapabiliyor.
- `api.py`: uygulamanın konuştuğu FastAPI sunucusu. `POST /evaluate` fotoğrafı `inputs/` içine kaydediyor, OMRChecker'ı çalıştırıyor, sonuç CSV'sini okuyor, öğrenciyi sınıf listesinde bulup notunu Excel dosyasına yazıyor.
- `inputs/`: bizim formun şablonu (`template.json`, `omr_marker.jpg`, `config.json`). 9 haneli öğrenci numarası ve A–E şıklı 20 soru var.
- `OMRChecker.spec`: taşınabilir Windows sürümü için PyInstaller ayarı. Derlenmiş hali `dist/OMRChecker/` içinde.

## Notlandırma

- Sınıf listesi, `Ogrenci_No` ve `Ad_Soyad` sütunları olan bir Excel dosyası. Panel bunu `sinif_listesi/ogrenciler.xlsx` olarak kopyalıyor.
- Cevap anahtarı bir metin dosyası; `1:A, 2:B, ...` şeklinde ya da düz `ABCDE...` olarak yazılabiliyor. `cevap_anahtari/cevaplar.txt` olarak kopyalanıyor.
- Her doğru cevap 5 puan (20 soru, toplam 100). Not, aynı Excel dosyasındaki `Not` sütununa yazılıyor.

Örnek dosyalar `samples/mySample/test_samples/` içinde (`students.xlsx`, `answers.txt`, `scan.jpg`).

## Çalıştırma

Bilgisayarda (Python 3.12):

```bash
pip install -r requirements.txt
python gui.py
```

Panelde sınıf listesini ve cevap anahtarını yükle, sonra **SUNUCUYU BAŞLAT**'a bas. Windows bağlantıyı engellerse **FIREWALL İZNİ VER** 8000 portu için güvenlik duvarı kuralı ekliyor. Telefonla bilgisayar aynı ağda olmalı.

Telefonda uygulamayı aç, paneldeki QR kodu okut, sonra formun fotoğrafını çekip kırp ve gönder.

Uygulamayı derlemek için:

```bash
cd omr_scanner_app
flutter pub get
flutter build apk
```

Taşınabilir Windows sürümü için `pip install pyinstaller` sonrası `pyinstaller OMRChecker.spec` yeterli; çıktı `dist/OMRChecker/OMRChecker.exe` olarak çıkıyor.

OMRChecker'ın kendi komut satırı da çalışmaya devam ediyor (`python main.py -i inputs`). Şablon formatı ve motorun geri kalanı için [orijinal README](https://github.com/Udayraj123/OMRChecker#readme) ile [wiki](https://github.com/Udayraj123/OMRChecker/wiki)'ye bakabilirsin.

## Notlar

- Tek bir form düzeni hazır. Farklı bir form için `inputs/template.json` dosyasını düzenle; 20 soru / 5 puan hesabını da `api.py` içinde (elle test için `gui.py` içinde) değiştir.
- Sunucuda kimlik doğrulama yok ve her kaynaktan gelen isteği kabul ediyor. Sadece güvendiğin bir ağda çalıştır.
- Arayüz (uygulama ve panel) Türkçe.

## Emeği geçenler ve lisans

OMR motoru, Udayraj Deshmukh ve katkıcıların geliştirdiği [OMRChecker](https://github.com/Udayraj123/OMRChecker). MIT lisansıyla yayınlanıyor (bkz. `LICENSE`).
