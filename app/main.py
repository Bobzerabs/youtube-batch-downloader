from __future__ import annotations

import asyncio
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DOWNLOADS_DIR = BASE_DIR.parent / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# FFmpeg portátil instalado pelo install.bat.
# Não depende do PATH do Windows.
FFMPEG_DIR = BASE_DIR.parent / "ffmpeg"
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_DIR / "ffprobe.exe"

APP_NAME = os.getenv("APP_NAME", "TubeBatch")
MAX_URLS = int(os.getenv("MAX_URLS_PER_BATCH", "0"))
INSPECT_WORKERS = max(1, int(os.getenv("INSPECT_WORKERS", "6")))
DOWNLOAD_WORKERS = max(1, int(os.getenv("DOWNLOAD_WORKERS", "3")))
JOB_TTL_HOURS = max(1, int(os.getenv("JOB_TTL_HOURS", "12")))

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.RLock()


def normalize_youtube_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("Link vazio.")

    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise ValueError("Apenas links do YouTube são aceitos.")

    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    elif parsed.path.startswith("/shorts/"):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) > 1 else None
    elif parsed.path.startswith("/live/"):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) > 1 else None
    elif parsed.path.startswith("/embed/"):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) > 1 else None

    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        raise ValueError("Link de vídeo/Short inválido.")

    return f"https://www.youtube.com/watch?v={video_id}"


class InspectRequest(BaseModel):
    urls: list[str] = Field(min_length=1)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: list[str]) -> list[str]:
        if MAX_URLS > 0 and len(value) > MAX_URLS:
            raise ValueError(f"Máximo de {MAX_URLS} links por lote.")
        return value


class DownloadItem(BaseModel):
    url: str
    mode: str = Field(pattern=r"^(mp4|mp3)$")
    quality: str = "best"
    audio_bitrate: str = "320"

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, value: str) -> str:
        if value == "best":
            return value
        if not value.isdigit():
            raise ValueError("Qualidade inválida.")
        q = int(value)
        if q < 144 or q > 4320:
            raise ValueError("Qualidade fora do intervalo permitido.")
        return value

    @field_validator("audio_bitrate")
    @classmethod
    def validate_bitrate(cls, value: str) -> str:
        if value not in {"128", "192", "256", "320"}:
            raise ValueError("Bitrate MP3 inválido.")
        return value


class DownloadRequest(BaseModel):
    items: list[DownloadItem] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def validate_items(cls, value: list[DownloadItem]) -> list[DownloadItem]:
        if MAX_URLS > 0 and len(value) > MAX_URLS:
            raise ValueError(f"Máximo de {MAX_URLS} itens por lote.")
        return value


def safe_text(value: Any, fallback: str = "") -> str:
    return str(value).strip() if value is not None else fallback


def format_duration(seconds: Any) -> int:
    try:
        return max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return 0


def inspect_one(raw_url: str) -> dict[str, Any]:
    url = normalize_youtube_url(raw_url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info or info.get("_type") == "playlist":
        raise ValueError("Não foi possível identificar um vídeo individual.")

    heights = set()
    for fmt in info.get("formats") or []:
        if fmt.get("vcodec") not in (None, "none") and fmt.get("height"):
            try:
                heights.add(int(fmt["height"]))
            except (TypeError, ValueError):
                pass

    qualities = sorted(heights, reverse=True)
    return {
        "url": url,
        "id": safe_text(info.get("id")),
        "title": safe_text(info.get("title"), "Vídeo do YouTube"),
        "channel": safe_text(info.get("channel") or info.get("uploader"), "YouTube"),
        "duration": format_duration(info.get("duration")),
        "thumbnail": safe_text(info.get("thumbnail")),
        "qualities": qualities,
        "is_short": "/shorts/" in raw_url.lower()
        or format_duration(info.get("duration")) <= 180,
    }


def get_job(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Lote não encontrado ou expirado.")
        return job


def update_job_item(job_id: str, index: int, **changes: Any) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["items"][index].update(changes)
        job["updated_at"] = time.time()
        completed = sum(
            1 for i in job["items"] if i["status"] in {"done", "error"}
        )
        total = max(1, len(job["items"]))
        job["progress"] = round((completed / total) * 100, 2)


def selector_for_quality(quality: str) -> str:
    if quality == "best":
        return (
            "bv*[ext=mp4]+ba[ext=m4a]/"
            "b[ext=mp4]/"
            "bv*+ba/b"
        )

    h = int(quality)
    return (
        f"bv*[height<=?{h}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<=?{h}][ext=mp4]/"
        f"bv*[height<=?{h}]+ba/"
        f"b[height<=?{h}]"
    )



def ensure_ffmpeg_available() -> None:
    if not FFMPEG_EXE.exists() or not FFPROBE_EXE.exists():
        raise RuntimeError(
            "FFmpeg portátil não encontrado. Execute install.bat novamente."
        )


def download_one(job_id: str, index: int, item: dict[str, Any], job_dir: Path) -> None:
    try:
        ensure_ffmpeg_available()
        url = normalize_youtube_url(item["url"])
        mode = item["mode"]
        quality = item.get("quality", "best")
        bitrate = item.get("audio_bitrate", "320")

        update_job_item(job_id, index, status="downloading", progress=1, error=None)

        def progress_hook(data: dict[str, Any]) -> None:
            if data.get("status") == "downloading":
                downloaded = data.get("downloaded_bytes") or 0
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                percent = round((downloaded / total) * 100, 1) if total else None
                update_job_item(
                    job_id,
                    index,
                    progress=percent if percent is not None else 5,
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                )
            elif data.get("status") == "finished":
                update_job_item(job_id, index, progress=96)

        output_template = str(job_dir / f"{index + 1:03d} - %(title).180B [%(id)s].%(ext)s")

        opts: dict[str, Any] = {
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "windowsfilenames": True,
            "progress_hooks": [progress_hook],
            "retries": 5,
            "fragment_retries": 5,
            "continuedl": True,
            "concurrent_fragment_downloads": 4,
            "ffmpeg_location": str(FFMPEG_DIR),
        }

        if mode == "mp3":
            opts.update(
                {
                    "format": "bestaudio/best",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": bitrate,
                        },
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        },
                        {
                            "key": "EmbedThumbnail",
                            "already_have_thumbnail": False,
                        },
                    ],
                    "writethumbnail": True,
                }
            )
        else:
            opts.update(
                {
                    "format": selector_for_quality(quality),
                    "merge_output_format": "mp4",
                    "postprocessors": [
                        {
                            "key": "FFmpegMetadata",
                            "add_metadata": True,
                        }
                    ],
                }
            )

        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(url, download=True)

        video_id = safe_text(result.get("id")) if result else ""
        candidates = [
            p for p in job_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in {".mp4", ".mp3"}
            and (not video_id or f"[{video_id}]" in p.name)
        ]
        if not candidates:
            candidates = [
                p for p in job_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".mp4", ".mp3"}
            ]

        if not candidates:
            raise RuntimeError("O arquivo final não foi encontrado após o processamento.")

        final_file = max(candidates, key=lambda p: p.stat().st_mtime)
        update_job_item(
            job_id,
            index,
            status="done",
            progress=100,
            filename=final_file.name,
            size=final_file.stat().st_size,
            speed=None,
            eta=0,
        )
    except Exception as exc:
        update_job_item(
            job_id,
            index,
            status="error",
            progress=100,
            error=str(exc)[:500],
            speed=None,
            eta=None,
        )


def build_archive(job_id: str) -> Path | None:
    job = get_job(job_id)
    job_dir = Path(job["directory"])
    files = [
        p for p in job_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".mp4", ".mp3"}
    ]

    if not files:
        return None

    archive = job_dir / f"{APP_NAME}-{job_id[:8]}.zip"
    if archive.exists():
        archive.unlink()

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, arcname=file.name)

    return archive


def run_download_job(job_id: str) -> None:
    job = get_job(job_id)
    items = job["items"]
    job_dir = Path(job["directory"])

    with jobs_lock:
        job["status"] = "running"
        job["updated_at"] = time.time()

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = [
            pool.submit(download_one, job_id, idx, item, job_dir)
            for idx, item in enumerate(items)
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass

    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        done_count = sum(1 for i in job["items"] if i["status"] == "done")
        error_count = sum(1 for i in job["items"] if i["status"] == "error")
        job["status"] = "done" if done_count else "error"
        job["progress"] = 100
        job["done_count"] = done_count
        job["error_count"] = error_count
        job["updated_at"] = time.time()

    if done_count:
        try:
            archive = build_archive(job_id)
            with jobs_lock:
                if archive and job_id in jobs:
                    jobs[job_id]["archive"] = archive.name
        except Exception:
            pass


def cleanup_old_jobs() -> None:
    cutoff = time.time() - (JOB_TTL_HOURS * 3600)
    stale: list[str] = []
    with jobs_lock:
        for job_id, job in jobs.items():
            if job.get("updated_at", 0) < cutoff:
                stale.append(job_id)

    for job_id in stale:
        with jobs_lock:
            job = jobs.pop(job_id, None)
        if job:
            shutil.rmtree(job["directory"], ignore_errors=True)


app = FastAPI(title=APP_NAME, version="1.0.0")


@app.get("/api/health")
def health() -> dict[str, Any]:
    cleanup_old_jobs()
    return {
        "ok": True,
        "app": APP_NAME,
        "max_urls_per_batch": MAX_URLS,
        "download_workers": DOWNLOAD_WORKERS,
    }


@app.post("/api/inspect")
async def inspect_videos(payload: InspectRequest) -> dict[str, Any]:
    cleanup_old_jobs()

    normalized_inputs = []
    seen = set()
    for raw in payload.urls:
        raw = raw.strip()
        if raw and raw not in seen:
            normalized_inputs.append(raw)
            seen.add(raw)

    loop = asyncio.get_running_loop()

    def perform() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = [None] * len(normalized_inputs)  # type: ignore
        with ThreadPoolExecutor(max_workers=INSPECT_WORKERS) as pool:
            future_map = {
                pool.submit(inspect_one, url): (idx, url)
                for idx, url in enumerate(normalized_inputs)
            }
            for future in as_completed(future_map):
                idx, original = future_map[future]
                try:
                    results[idx] = {"ok": True, **future.result()}
                except Exception as exc:
                    results[idx] = {
                        "ok": False,
                        "url": original,
                        "error": str(exc)[:500],
                    }
        return results

    results = await loop.run_in_executor(None, perform)
    return {"results": results, "count": len(results)}


@app.post("/api/download")
def create_download(payload: DownloadRequest) -> dict[str, Any]:
    cleanup_old_jobs()

    job_id = uuid.uuid4().hex
    job_dir = DOWNLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    items: list[dict[str, Any]] = []
    for source in payload.items:
        try:
            normalized = normalize_youtube_url(source.url)
        except ValueError as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        items.append(
            {
                "url": normalized,
                "mode": source.mode,
                "quality": source.quality,
                "audio_bitrate": source.audio_bitrate,
                "status": "queued",
                "progress": 0,
                "filename": None,
                "size": None,
                "speed": None,
                "eta": None,
                "error": None,
            }
        )

    now = time.time()
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "directory": str(job_dir),
            "items": items,
            "archive": None,
            "done_count": 0,
            "error_count": 0,
        }

    thread = threading.Thread(target=run_download_job, args=(job_id,), daemon=True)
    thread.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "items": len(items),
    }


@app.get("/api/job/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    cleanup_old_jobs()
    job = get_job(job_id)

    with jobs_lock:
        safe_job = {
            "id": job["id"],
            "status": job["status"],
            "progress": job["progress"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "items": [dict(item) for item in job["items"]],
            "archive_ready": bool(job.get("archive")),
            "done_count": job.get("done_count", 0),
            "error_count": job.get("error_count", 0),
        }
    return safe_job


@app.get("/api/job/{job_id}/archive")
def download_archive(job_id: str) -> FileResponse:
    job = get_job(job_id)
    archive_name = job.get("archive")
    if not archive_name:
        archive = build_archive(job_id)
        if not archive:
            raise HTTPException(status_code=404, detail="Nenhum arquivo pronto para baixar.")
        archive_name = archive.name
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["archive"] = archive_name

    archive_path = Path(job["directory"]) / archive_name
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo ZIP não encontrado.")

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=archive_path.name,
    )


@app.get("/api/job/{job_id}/file/{index}")
def download_single(job_id: str, index: int) -> FileResponse:
    job = get_job(job_id)
    if index < 0 or index >= len(job["items"]):
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    item = job["items"][index]
    if item["status"] != "done" or not item.get("filename"):
        raise HTTPException(status_code=409, detail="Arquivo ainda não está pronto.")

    path = Path(job["directory"]) / item["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    media_type = "audio/mpeg" if path.suffix.lower() == ".mp3" else "video/mp4"
    return FileResponse(path, media_type=media_type, filename=path.name)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
