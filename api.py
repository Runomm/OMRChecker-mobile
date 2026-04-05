"""
OMRChecker FastAPI Wrapper
==========================
Exposes a single POST /evaluate endpoint that:
  1. Accepts an image via multipart/form-data
  2. Saves it into the `inputs/` directory along with the template files
  3. Runs OMRChecker via subprocess
  4. Parses the generated CSV from `outputs/`
  5. Returns the result as a JSON response

Run with:
    python -m uvicorn api:app --host 0.0.0.0 --port 8000

Install dependencies:
    pip install fastapi uvicorn python-multipart pandas

Configure TEMPLATE_DIR below to point to the folder containing your
template.json (and omr_marker.jpg if used).
"""

import asyncio
import glob
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("omr-api")

# ---------------------------------------------------------------------------
# Path constants  — adjust TEMPLATE_DIR to match your sheet design
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
INPUTS_DIR = BASE_DIR / "inputs"
OUTPUTS_DIR = BASE_DIR / "outputs"
MAIN_SCRIPT = BASE_DIR / "main.py"

CEVAP_ANAHTARI_DIR = BASE_DIR / "cevap_anahtari"
SINIF_LISTESI_DIR = BASE_DIR / "sinif_listesi"

CEVAP_ANAHTARI_DIR.mkdir(exist_ok=True)
SINIF_LISTESI_DIR.mkdir(exist_ok=True)

# Template files (template.json, omr_marker.jpg, config.json) must be statically placed in inputs/

# OMRChecker mirrors the input tree under outputs/, so we glob recursively.
# e.g. outputs/Results/Results_09AM.csv  OR  outputs/inputs/Results/Results_09AM.csv
RESULTS_GLOB = str(OUTPUTS_DIR / "**" / "Results_*.csv")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="OMRChecker API",
    description="REST wrapper for the OMRChecker bubble-sheet grader.",
    version="1.0.0",
)

# Allow any origin — tighten this in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_inputs_dir() -> None:
    """Remove previous incoming camera scans from inputs/ without touching template files."""
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove prev scans (they are saved as scan.jpg, scan.png, etc) to prevent grading them again
    for item in INPUTS_DIR.iterdir():
        if item.is_file() and item.name.lower().startswith("scan"):
            try:
                item.unlink()
                log.info("Deleted stale scan image: %s", item.name)
            except Exception as exc:
                log.warning("Could not delete stale scan image %s: %s", item.name, exc)


def _find_latest_csv() -> Path | None:
    """
    Return the most-recently modified Results CSV, or None if none exists.

    OMRChecker names the file Results_<HOUR>.csv so in edge cases there could
    be multiple files; we take the newest one.
    """
    matches = glob.glob(RESULTS_GLOB, recursive=True)
    if not matches:
        return None
    return Path(max(matches, key=os.path.getmtime))


def _parse_csv(csv_path: Path) -> list[dict[str, Any]]:
    """
    Parse the OMRChecker Results CSV and return a list of row dicts.

    The CSV has the columns:
        file_id, input_path, output_path, score, <template columns…>

    We expose everything except the raw filesystem paths.
    """
    df = pd.read_csv(csv_path, dtype=str)

    # Drop internal path columns — keep everything else.
    drop_cols = [c for c in ("input_path", "output_path") if c in df.columns]
    df = df.drop(columns=drop_cols)

    # Forward-fill NaN so JSON serialisation doesn't produce nulls for empty bubbles.
    df = df.fillna("")

    records = df.to_dict(orient="records")
    return records


async def _run_omrchecker() -> tuple[int, str, str]:
    """
    Execute `python main.py` as a subprocess and return (returncode, stdout, stderr).
    Runs in a thread pool so the event loop is never blocked.
    """
    log.info("Spawning OMRChecker subprocess…")

    loop = asyncio.get_event_loop()
    proc = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            [sys.executable, str(MAIN_SCRIPT)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=120,          # 2-minute hard timeout
        ),
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/evaluate",
    summary="Evaluate an OMR sheet image",
    response_description="Parsed results from the OMR sheet",
)
async def evaluate(file: UploadFile = File(..., description="OMR sheet image (JPG/PNG)")):
    """
    Accept a bubble-sheet image, run OMRChecker, and return the results as JSON.

    **Steps:**
    1. Validate the uploaded file is an image.
    2. Clear `inputs/` and save the new image there.
    3. Run `python main.py` via subprocess.
    4. Locate and parse the generated Results CSV.
    5. Return the parsed rows as a JSON array.
    """

    # ------------------------------------------------------------------
    # 1. Validate file type
    # ------------------------------------------------------------------
    allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Upload a JPG or PNG image.",
        )

    # ------------------------------------------------------------------
    # 2. Save image to inputs/
    # ------------------------------------------------------------------
    try:
        _clear_inputs_dir()
    except Exception as exc:
        log.exception("Failed to clear inputs directory")
        raise HTTPException(status_code=500, detail=f"Could not clear inputs dir: {exc}")

    # Preserve the original extension
    suffix = Path(file.filename or "image.jpg").suffix or ".jpg"
    dest_path = INPUTS_DIR / f"scan{suffix}"
    try:
        contents = await file.read()
        dest_path.write_bytes(contents)
        log.info("Saved uploaded image → %s  (%d bytes)", dest_path, len(contents))
    except Exception as exc:
        log.exception("Failed to save uploaded file")
        raise HTTPException(status_code=500, detail=f"Could not save upload: {exc}")

    # ------------------------------------------------------------------
    # 3. Run OMRChecker
    # ------------------------------------------------------------------
    try:
        returncode, stdout, stderr = await _run_omrchecker()
    except subprocess.TimeoutExpired:
        log.error("OMRChecker timed out")
        raise HTTPException(status_code=504, detail="OMRChecker processing timed out.")
    except Exception as exc:
        log.exception("Subprocess error")
        raise HTTPException(status_code=500, detail=f"Subprocess error: {exc}")

    log.info("OMRChecker exited with code %d", returncode)
    if stdout:
        log.debug("STDOUT:\n%s", stdout)
    if stderr:
        log.debug("STDERR:\n%s", stderr)

    if returncode != 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "OMRChecker failed",
                "returncode": returncode,
                "stderr": stderr[-2000:],   # last 2 000 chars only
            },
        )

    # ------------------------------------------------------------------
    # 4. Locate the Results CSV
    # ------------------------------------------------------------------
    csv_path = _find_latest_csv()
    if csv_path is None:
        log.error("No Results CSV found under %s", OUTPUTS_DIR)
        raise HTTPException(
            status_code=500,
            detail=(
                "OMRChecker ran successfully but no Results CSV was produced. "
                "Check that a valid template.json is present in the inputs directory."
            ),
        )
    log.info("Parsing results from: %s", csv_path)

    # ------------------------------------------------------------------
    # 5. Parse and return
    # ------------------------------------------------------------------
    try:
        records = _parse_csv(csv_path)
    except Exception as exc:
        log.exception("Failed to parse CSV")
        raise HTTPException(status_code=500, detail=f"Could not parse results CSV: {exc}")

    if not records:
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "message": "Processing succeeded but no rows found in the CSV.",
                "results": [],
            },
        )

    last_row = records[-1]

    # --- 1. Reconstruct Student Number (Ogrenci_No) ---
    roll = str(last_row.get("Roll", last_row.get("roll", ""))).strip()
    if not roll or roll.lower() == "nan":
        roll_chars = []
        for i in range(1, 10):
            val = str(last_row.get(f"H{i}", "")).strip()
            # In cases where H1-H9 have marks, collect them
            if val and val.lower() != "nan":
                roll_chars.append(val)
        roll = "".join(roll_chars)
        
    if not roll:
        raise HTTPException(status_code=400, detail="Öğrenci numarası (Ogrenci_No) OMR kağıdında algılanamadı.")

    # --- 2. Evaluate Student in Excel ---
    ogrenciler_path = SINIF_LISTESI_DIR / "ogrenciler.xlsx"
    if not ogrenciler_path.exists():
        log.error("ogrenciler.xlsx is missing!")
        raise HTTPException(status_code=500, detail="sinif_listesi/ogrenciler.xlsx bulunamadı.")
        
    try:
        df = pd.read_excel(ogrenciler_path, dtype=str)
        df.columns = df.columns.str.strip()
    except Exception as exc:
        log.error("Failed to read Excel: %s", exc)
        raise HTTPException(status_code=500, detail="ogrenciler.xlsx okunamadı.")
        
    if "Ogrenci_No" not in df.columns or "Ad_Soyad" not in df.columns:
        raise HTTPException(status_code=500, detail="Excel dosyasında 'Ogrenci_No' veya 'Ad_Soyad' sütunu eksik.")

    df["Ogrenci_No"] = df["Ogrenci_No"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    match_idx = df.index[df["Ogrenci_No"] == str(roll).strip()].tolist()
    
    if not match_idx:
        raise HTTPException(status_code=404, detail=f"{roll} no lu öğrenci bulunamadı")
        
    idx = match_idx[0]
    ad_soyad = df.at[idx, "Ad_Soyad"]

    # --- 3. Read Answer Key ---
    ans_file = CEVAP_ANAHTARI_DIR / "cevaplar.txt"
    if not ans_file.exists():
        log.error("cevaplar.txt is missing!")
        raise HTTPException(status_code=500, detail="cevap_anahtari/cevaplar.txt bulunamadı.")
    
    try:
        with open(ans_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        import re
        if ":" in content or "-" in content:
            # Parse format like "1:A, 2:B" or "1-A"
            parts = re.split(r'[,\n\r]+', content)
            ans_dict = {}
            for part in parts:
                part = part.strip()
                if not part: continue
                kv = re.split(r'[:\-]', part)
                if len(kv) >= 2:
                    q_num = re.sub(r'\D', '', kv[0])
                    if q_num:
                        ans_dict[int(q_num)] = kv[1].strip().upper()
            # Convert to a flat 20-character string for uniform grading
            answer_key = "".join(ans_dict.get(i, "X") for i in range(1, 21))
        else:
            # Parse format like "ABCDEABCDE"
            answer_key = re.sub(r'\s+', '', content).upper()
            
    except Exception as exc:
        log.error("Failed to read cevaplar.txt: %s", exc)
        raise HTTPException(status_code=500, detail="cevaplar.txt okunamadı veya format hatalı.")

    # --- 4. Parse Answers & Grade (20 questions, 5 points each) ---
    correct_answers_count = 0
    total_q = min(len(answer_key), 20)
    
    for i in range(total_q):
        q_key_S = f"S{i+1}"
        q_key_q = f"q{i+1}"
        val = str(last_row.get(q_key_S, last_row.get(q_key_q, ""))).strip().upper()
        if val and val.lower() != "nan" and val == answer_key[i]:
            correct_answers_count += 1
            
    score = correct_answers_count * 5

    # --- 5. Update Excel ---
    if "Not" not in df.columns:
        df["Not"] = ""
    df.at[idx, "Not"] = str(score)
    df.to_excel(ogrenciler_path, index=False)
    log.info("Student %s (%s) scored %s. Excel updated.", roll, ad_soyad, score)

    # --- 6. JSON Response Formulation ---
    # The UI will ONLY read 'Sonuç' via the extras mapping since we drop raw column dumps.
    success_message = f"{roll} numaralı, {ad_soyad}'ın notu işlendi: {score}"
    
    return JSONResponse(
        content={
            "status": "ok",
            "roll_number": roll,
            "Ad_Soyad": ad_soyad,
            "score": score,
            "results": [{"Sonuç": success_message}],
        }
    )


# ---------------------------------------------------------------------------
# Health-check
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check", include_in_schema=False)
async def health():
    return {"status": "healthy"}
