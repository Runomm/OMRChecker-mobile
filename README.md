# OMRChecker Mobile

[Türkçe](README.tr.md)

This is a fork of [Udayraj123/OMRChecker](https://github.com/Udayraj123/OMRChecker) with a phone app and a small desktop panel added on top. The use case is simple: a teacher photographs answer sheets with a phone, and the grades are written into an Excel class list on the PC.

The bubble detection is OMRChecker's own. What this fork adds:

- `omr_scanner_app/`: a Flutter app for Android. You scan the QR code shown on the PC, photograph a sheet, crop it and send it. The app then shows the student number and the grade.
- `gui.py`: a desktop control panel (CustomTkinter). It starts the server, shows the PC's local IP and a QR code for the app, loads the class list and the answer key, and can run a manual test on the images in `inputs/`.
- `api.py`: the FastAPI server the app talks to. `POST /evaluate` saves the photo into `inputs/`, runs OMRChecker, reads the result CSV, finds the student in the class list and writes the grade into the Excel file.
- `inputs/`: the template for our sheet (`template.json`, `omr_marker.jpg`, `config.json`): a 9-digit student number and 20 questions with options A–E.
- `OMRChecker.spec`: PyInstaller config for a portable Windows build. A built copy is in `dist/OMRChecker/`.

## Grading

- The class list is an Excel file with `Ogrenci_No` (student number) and `Ad_Soyad` (name) columns. The panel copies it to `sinif_listesi/ogrenciler.xlsx`.
- The answer key is a text file, written either as `1:A, 2:B, ...` or simply `ABCDE...`. It's copied to `cevap_anahtari/cevaplar.txt`.
- Each correct answer is worth 5 points (20 questions, 100 in total). The grade is written into a `Not` (grade) column in the same Excel file.

Example files are in `samples/mySample/test_samples/` (`students.xlsx`, `answers.txt`, `scan.jpg`).

## Running it

On the PC (Python 3.12):

```bash
pip install -r requirements.txt
python gui.py
```

In the panel, load the class list and the answer key, then click **SUNUCUYU BAŞLAT** (start server). If Windows blocks the connection, **FIREWALL İZNİ VER** adds a firewall rule for port 8000. The phone and the PC need to be on the same network.

On the phone, open the app, scan the QR code from the panel, then photograph a sheet, crop it and send it.

Building the app:

```bash
cd omr_scanner_app
flutter pub get
flutter build apk
```

Building the portable Windows version (needs `pip install pyinstaller`): `pyinstaller OMRChecker.spec`. The output goes to `dist/OMRChecker/OMRChecker.exe`.

OMRChecker's own command line still works (`python main.py -i inputs`). For the template format and the rest of the engine, see the [upstream README](https://github.com/Udayraj123/OMRChecker#readme) and [wiki](https://github.com/Udayraj123/OMRChecker/wiki).

## Notes

- Only one sheet layout is set up. For a different sheet, edit `inputs/template.json`, and change the 20-question, 5-point grading in `api.py` (and in `gui.py` for the manual test).
- The server has no authentication and accepts requests from any origin. Only run it on a network you trust.
- The interface (app and panel) is in Turkish.

## Credits and license

The OMR engine is [OMRChecker](https://github.com/Udayraj123/OMRChecker) by Udayraj Deshmukh and contributors, released under the MIT license (see `LICENSE`).
