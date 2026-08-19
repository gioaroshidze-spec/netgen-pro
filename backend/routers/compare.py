from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import os, difflib
from typing import Optional
from routers.auth import get_current_user
from config_compare import normalize_config_for_comparison

router = APIRouter(tags=["Archive & Compare"])
ARCHIVE_DIR = os.getenv("VNMS_ARCHIVE_DIR", "archive")

@router.get("/archive/files")
def get_archive_files(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not os.path.exists(ARCHIVE_DIR):
        return {}
    
    files = os.listdir(ARCHIVE_DIR)
    devices = db.query(models.NetworkDevice).all()
    grouped_files = {}

    for f in files:
        if not f.endswith(".txt"):
            continue
            
        matched_device = None
        for dev in devices:
            if f"_{dev.hostname}_" in f:
                matched_device = dev
                break
        
        if matched_device:
            os_t = matched_device.os_type or "UnknownOS"
            dev_t = matched_device.device_type or "UnknownDevice"
            host = matched_device.hostname
        else:
            os_t = "Unassigned"
            dev_t = "Unknown"
            host = "Orphaned_Files"

        if os_t not in grouped_files:
            grouped_files[os_t] = {}
        if dev_t not in grouped_files[os_t]:
            grouped_files[os_t][dev_t] = {}
        if host not in grouped_files[os_t][dev_t]:
            grouped_files[os_t][dev_t][host] = []

        grouped_files[os_t][dev_t][host].append(f)
    
    for os_t in grouped_files:
        for dev_t in grouped_files[os_t]:
            for host in grouped_files[os_t][dev_t]:
                grouped_files[os_t][dev_t][host].sort(reverse=True)

    return grouped_files


@router.post("/compare/")
async def compare_configs(
    upload_file1: Optional[UploadFile] = File(None),
    archive_file1: Optional[str] = Form(None),
    current_user: models.User = Depends(get_current_user),
    upload_file2: Optional[UploadFile] = File(None),
    archive_file2: Optional[str] = Form(None),
):
    config1 = ""
    config2 = ""

    # --- RESOLVE FILE 1 (Left Side) ---
    if upload_file1:
        config1 = (await upload_file1.read()).decode('utf-8', errors='ignore')
        desc1 = upload_file1.filename
    elif archive_file1:
        # SECURED: Strip path traversal attempts
        safe_file1 = os.path.basename(archive_file1)
        path1 = os.path.join(ARCHIVE_DIR, safe_file1)
        if not os.path.exists(path1):
            raise HTTPException(status_code=404, detail="File 1 not found in archive.")
        with open(path1, "r", encoding="utf-8", errors="ignore") as f1:
            config1 = f1.read()
        desc1 = safe_file1
    else:
        raise HTTPException(status_code=400, detail="Missing File 1")

    # --- RESOLVE FILE 2 (Right Side) ---
    if upload_file2:
        config2 = (await upload_file2.read()).decode('utf-8', errors='ignore')
        desc2 = upload_file2.filename
    elif archive_file2:
        # SECURED: Strip path traversal attempts
        safe_file2 = os.path.basename(archive_file2)
        path2 = os.path.join(ARCHIVE_DIR, safe_file2)
        if not os.path.exists(path2):
            raise HTTPException(status_code=404, detail="File 2 not found in archive.")
        with open(path2, "r", encoding="utf-8", errors="ignore") as f2:
            config2 = f2.read()
        desc2 = safe_file2
    else:
        raise HTTPException(status_code=400, detail="Missing File 2")

    # --- SMART SCRUBBER ---
    config1 = normalize_config_for_comparison(config1)
    config2 = normalize_config_for_comparison(config2)

    if config1 == config2:
        return {"match": True, "html": "<div style='padding: 20px; color: #4caf50; font-weight: bold; text-align: center;'>✅ Configurations are a 100% perfect match. Zero drift detected.</div>"}
    
    # Generate highlighted HTML diff
    diff_lines = list(difflib.unified_diff(
        config1.splitlines(),
        config2.splitlines(),
        fromfile=desc1,
        tofile=desc2,
        n=3
    ))

    html_output = "<pre style='font-family: monospace; font-size: 14px; line-height: 1.4;'>"
    for line in diff_lines:
        safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if safe_line.startswith("---") or safe_line.startswith("+++"):
            html_output += f"<strong style='color: #fff;'>{safe_line}</strong>\n"
        elif safe_line.startswith("@@"):
            html_output += f"<span style='color: #aaa;'>{safe_line}</span>\n"
        elif safe_line.startswith("-"):
            html_output += f"<span style='color: #4caf50;'>{safe_line}</span>\n"  # Baseline = Green
        elif safe_line.startswith("+"):
            html_output += f"<span style='color: #007acc;'>{safe_line}</span>\n"  # Target = Blue
        else:
            html_output += f"<span style='color: #d4d4d4;'>{safe_line}</span>\n"
    html_output += "</pre>"

    return {"match": False, "html": html_output}
