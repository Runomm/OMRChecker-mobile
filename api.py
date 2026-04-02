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

# Directory that contains template.json (and omr_marker.jpg, config.json, …)
# These files are copied into inputs/ before every run.
TEMPLATE_DIR = BASE_DIR / "samples" / "sample1"

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
    """Remove all image/csv files inside inputs/, then copy fresh template files in."""
    import json as _json

    INPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove only image / output files — leave existing template files for now
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    for item in INPUTS_DIR.iterdir():
        if item.is_file() and item.suffix.lower() in image_exts:
            item.unlink()
            log.info("Deleted stale image: %s", item.name)

    # Copy template support files (template.json, omr_marker.jpg, config.json, …)
    # from TEMPLATE_DIR into INPUTS_DIR so OMRChecker can find them.
    template_files = [".json", ".jpg", ".jpeg", ".png"]
    for src in TEMPLATE_DIR.iterdir():
        if src.is_file() and src.suffix.lower() in template_files:
            dst = INPUTS_DIR / src.name
            shutil.copy2(src, dst)
            log.info("Copied template file: %s", src.name)

    # --- Headless override ---------------------------------------------------
    # Always write a config.json that disables all GUI windows.
    # show_image_level=0  →  OMRChecker never calls cvShowImage.
    config_dst = INPUTS_DIR / "config.json"
    headless_config: dict = {"outputs": {"show_image_level": 0}}

    # Preserve display/processing dimensions from the template's config if present
    template_config_src = TEMPLATE_DIR / "config.json"
    if template_config_src.exists():
        try:
            with open(template_config_src) as f:
                orig = _json.load(f)
            if "dimensions" in orig:
                headless_config["dimensions"] = orig["dimensions"]
        except Exception:
            pass  # safe to ignore; OMRChecker uses defaults

    with open(config_dst, "w") as f:
        _json.dump(headless_config, f, indent=2)
    log.info("Wrote headless config.json (show_image_level=0)")


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

    # For convenience: surface the first row's Roll and score at the top level,
    # and return all rows in the `results` array for multi-sheet batches.
    first = records[0]
    roll = first.get("Roll", first.get("roll", "N/A"))
    score = first.get("score", "N/A")

    # 1 & 2. Find Isim from ogrenciler.csv
    isim = "Bilinmeyen Ogrenci"
    try:
        ogrenciler_path = BASE_DIR / "ogrenciler.csv"
        if ogrenciler_path.exists():
            ogrenciler_df = pd.read_csv(ogrenciler_path, dtype=str)
            # Ensure safe stripping of whitespace just in case
            ogrenciler_df.columns = ogrenciler_df.columns.str.strip()
            if "Ogrenci_No" in ogrenciler_df.columns and "Isim" in ogrenciler_df.columns:
                match = ogrenciler_df[ogrenciler_df["Ogrenci_No"] == str(roll).strip()]
                if not match.empty:
                    isim = match.iloc[0]["Isim"]
    except Exception as exc:
        log.warning("Could not read ogrenciler.csv or find student: %s", exc)

    # 3. Append to final_notlar.csv
    import datetime
    try:
        final_file = BASE_DIR / "final_notlar.csv"
        file_exists = final_file.exists()
        with open(final_file, "a", encoding="utf-8") as f:
            if not file_exists:
                f.write("Ogrenci_No,Isim,Score,Tarih\n")
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Replace commas in isim to avoid breaking CSV format
            safe_isim = str(isim).replace(",", " ")
            f.write(f"{roll},{safe_isim},{score},{now_str}\n")
    except Exception as exc:
        log.error("Could not write to final_notlar.csv: %s", exc)

    # 4. Include 'isim' in JSON response
    return JSONResponse(
        content={
            "status": "ok",
            "roll_number": roll,
            "isim": isim,
            "score": score,
            "results": records,
        }
    )


# ---------------------------------------------------------------------------
# Health-check
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check", include_in_schema=False)
async def health():
    return {"status": "healthy"}
