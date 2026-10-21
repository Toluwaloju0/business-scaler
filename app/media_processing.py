"""Database-backed video analysis queue and local Gemma 4 E4B worker.

Run a worker separately from the API with ``python -m app.media_processing``.
Model weights must be present in the configured local model directory.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import json
import logging
import subprocess
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.models import AssetAnalysis, ContentAsset, ContentChunk, ProcessingJob, utc_now
from app.settings import get_settings

logger = logging.getLogger(__name__)
JOB_TYPE = "analyze_video"
MAX_ATTEMPTS = 3
POLL_INTERVAL_SECONDS = 3
WORKER_LEASE_SECONDS = 15 * 60


@lru_cache(maxsize=1)
def _load_local_gemma() -> tuple[Any, Any]:
    """Download missing Gemma files to disk, then load the local model once."""
    settings = get_settings()
    model_path = Path(settings.gemma_model_path).expanduser().resolve()

    try:
        import torch  # noqa: F401 - verify the local inference runtime is installed
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForMultimodalLM, AutoProcessor
    except ImportError as exc:
        raise RuntimeError(
            "Gemma inference requires torch, transformers, accelerate, and huggingface-hub"
        ) from exc

    required_files_present = (
        (model_path / "config.json").is_file()
        and (model_path / "processor_config.json").is_file()
        and (model_path / "tokenizer.json").is_file()
        and any(model_path.glob("*.safetensors"))
    )
    if not required_files_present:
        model_path.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Downloading Hugging Face model %s into %s",
            settings.gemma_model_repo_id,
            model_path,
        )
        try:
            snapshot_download(
                repo_id=settings.gemma_model_repo_id,
                local_dir=str(model_path),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not download {settings.gemma_model_repo_id} from Hugging Face "
                f"into {model_path}; check network access and available disk space"
            ) from exc

        required_files_present = (
            (model_path / "config.json").is_file()
            and (model_path / "processor_config.json").is_file()
            and (model_path / "tokenizer.json").is_file()
            and any(model_path.glob("*.safetensors"))
        )
        if not required_files_present:
            raise RuntimeError(f"Downloaded model files are incomplete in {model_path}")

    processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True)
    model = AutoModelForMultimodalLM.from_pretrained(
        str(model_path),
        dtype="auto",
        device_map="cpu",
        local_files_only=True,
    )

    meta_params = [
        name for name, param in model.named_parameters()
        if param.device.type == "meta"
    ]

    meta_buffers = [
        name for name, buf in model.named_buffers()
        if buf.device.type == "meta"
    ]

    print("="*100)
    print("Device map:", getattr(model, "hf_device_map", None))
    print("Meta parameters:", len(meta_params))
    print("Meta parameter examples:", meta_params[:10])
    print("Meta buffers:", len(meta_buffers))
    print("Meta buffer examples:", meta_buffers[:10])
    print("="*100)
    model.eval()
    return processor, model


def enqueue_video_analysis(db: Session, asset: ContentAsset) -> ProcessingJob:
    """Add a video analysis job to the caller's transaction; the caller commits."""
    if asset.asset_type != "video":
        raise ValueError("Only video assets can be added to the video analysis queue")
    if not asset.object_key:
        raise ValueError("Video asset must have a stored object key before enqueueing")

    job = ProcessingJob(
        business_id=asset.business_id,
        asset_id=asset.id,
        job_type=JOB_TYPE,
        state="pending",
    )
    asset.status = "processing"
    db.add(job)
    return job


def _media_path(object_key: str) -> Path:
    """Resolve a database storage key and reject paths outside the media directory."""
    root = Path(get_settings().media_storage_dir).resolve()
    media_path = (root / object_key).resolve()
    if media_path.parent != root:
        raise ValueError("Invalid media storage key")
    if not media_path.is_file():
        raise FileNotFoundError("Uploaded video file is missing")
    return media_path


def _extract_video_frames(video_path: Path) -> list[tuple[int, bytes]]:
    """Extract a bounded set of timestamped frames with ffmpeg."""
    settings = get_settings()
    interval = max(1, settings.video_frame_interval_seconds)
    frame_limit = max(1, settings.video_max_frames)
    frames: list[tuple[int, bytes]] = []

    with tempfile.TemporaryDirectory(prefix="localbiz-video-") as temporary_dir:
        frame_pattern = str(Path(temporary_dir) / "frame_%04d.jpg")
        command = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(video_path),
            "-vf", f"fps=1/{interval},scale=768:768:force_original_aspect_ratio=decrease",
            "-frames:v", str(frame_limit), "-q:v", "5", frame_pattern,
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=180)
        except FileNotFoundError as exc:
            print(exc)
            raise RuntimeError("ffmpeg is required by the media analysis worker") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Video frame extraction timed out") from exc
        except subprocess.CalledProcessError as exc:
            logger.warning("ffmpeg could not decode uploaded video (exit %s)", exc.returncode)
            raise RuntimeError("Video frame extraction failed") from exc

        for index, frame_path in enumerate(sorted(Path(temporary_dir).glob("frame_*.jpg"))):
            frames.append((index * interval, frame_path.read_bytes()))

    if not frames:
        raise RuntimeError("No frames could be extracted from the uploaded video")
    return frames


def _model_input_device(model: Any) -> Any:
    """Return where input tokens should execute for an Accelerate-dispatched model.

    Accelerate keeps offloaded embedding weights on ``meta`` between forward
    passes. Its hook records where those weights are materialized for execution.
    """
    import torch

    embedding_layer = model.get_input_embeddings()
    if embedding_layer is None:
        raise RuntimeError("Gemma model does not expose an input embedding layer")

    device = embedding_layer.weight.device
    if device.type != "meta":
        logger.info("The device is %s at line 170", device)
        return device

    # For disk/CPU offloaded weights, the parameter stays on meta until the
    # Accelerate pre-forward hook materializes it on its execution device.
    hook = getattr(embedding_layer, "_hf_hook", None)
    hooks = getattr(hook, "hooks", [hook]) if hook is not None else []
    for attached_hook in hooks:
        execution_device = getattr(attached_hook, "execution_device", None)
        if execution_device is None:
            continue
        if isinstance(execution_device, int):
            execution_device = f"cuda:{execution_device}"
        execution_device = torch.device(execution_device)
        if execution_device.type != "meta":
            logger.info("The device is %s at line 184", execution_device.type)
            return execution_device

    # A non-disk entry for the input embedding is a valid fallback for device
    # maps that do not expose an execution device through a module hook.
    device_map = getattr(model, "hf_device_map", {})
    embedding_name = next(
        (name for name, module in model.named_modules() if module is embedding_layer),
        None,
    )
    if embedding_name is not None:
        matching_names = [
            name for name in device_map
            if embedding_name == name or embedding_name.startswith(f"{name}.")
        ]
        if matching_names:
            mapped_device = device_map[max(matching_names, key=len)]
            logger.info("The device is %s at line 200", mapped_device)

            if mapped_device != "disk" and mapped_device != "meta":
                if isinstance(mapped_device, int):
                    mapped_device = f"cuda:{mapped_device}"
                return torch.device(mapped_device)

    raise RuntimeError(
        "Gemma input embeddings are on meta and Accelerate did not provide an "
        "execution device. Check the model's hf_device_map and offload hooks."
    )


def _call_gemma(video_path: Path) -> dict[str, Any]:
    """Analyze timestamped frames with Gemma loaded from local model files."""
    settings = get_settings()
    processor, model = _load_local_gemma()
    logger.info("processor and model loaded successfully")
    frames = _extract_video_frames(video_path)
    prompt = (
        "Analyze these ordered frames sampled from a short video. Timestamps are seconds from the start. "
        "Describe only visible evidence; do not infer identities, intent, or results that are not shown. "
        "Return a JSON object with keys: summary (string), scenes (array of objects with timestamp_seconds "
        "and description), visible_text (array of strings), tags (array of short strings), and uncertainty "
        "(array of strings). Make the summary useful for creating accurate social media content for a local business."
    )
    from PIL import Image

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for timestamp, frame_bytes in frames:
        content.append({"type": "text", "text": f"Frame timestamp: {timestamp} seconds"})
        image = Image.open(BytesIO(frame_bytes)).convert("RGB")
        content.append({"type": "image", "image": image})
    logger.info("The processed file images / frame has been completed passing to the model now")

    try:
        input_device = _model_input_device(model)
        inputs = processor.apply_chat_template(
            [{"role": "user", "content": content}],
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            add_generation_prompt=True,
        ).to(input_device)
        input_token_count = inputs["input_ids"].shape[-1]
        logger.info("The inputs has been set. moving on to generating model answers now.")
    
        import torch
        import time

        start = time.now()

        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=1200,
                do_sample=False,
            )
        logger.info("The model has generated an output %s", outputs)
        completion_time = time.now() = start
        loggger.info("Time taken to complete generation of answers = %s seconds", completion_time)
        message = processor.decode(outputs[0][input_token_count:], skip_special_tokens=True).strip()
        if message.startswith("```"):
            message = message.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        analysis = json.loads(message)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.error(exc)
        raise RuntimeError("Gemma returned an invalid analysis response") from exc

    if not isinstance(analysis, dict) or not isinstance(analysis.get("summary"), str):
        raise RuntimeError("Gemma analysis response is missing its summary")
    return analysis


def analyze_video(db: Session, asset: ContentAsset) -> AssetAnalysis:
    """Run Gemma on a saved video and persist the analysis and retrieval text chunks."""
    if asset.asset_type != "video" or not asset.object_key:
        raise ValueError("A stored video asset is required for analysis")

    settings = get_settings()
    analysis_data = _call_gemma(_media_path(asset.object_key))
    scenes = analysis_data.get("scenes")
    scenes = scenes if isinstance(scenes, list) else []
    tags = analysis_data.get("tags")
    tags = [str(tag)[:120] for tag in tags if isinstance(tag, (str, int, float))] if isinstance(tags, list) else []
    extracted_text = json.dumps(analysis_data, ensure_ascii=False)

    analysis = AssetAnalysis(
        asset_id=asset.id,
        processor_name="gemma-4-e4b",
        processor_version=Path(settings.gemma_model_path).name,
        extracted_text=extracted_text,
        tags=tags,
        quality_scores={"uncertainty": analysis_data.get("uncertainty", [])},
        status="complete",
    )
    db.add(analysis)
    db.flush()

    chunk_texts = [analysis_data["summary"]]
    for scene in scenes:
        if isinstance(scene, dict) and isinstance(scene.get("description"), str):
            timestamp = scene.get("timestamp_seconds")
            chunk_texts.append(f"At {timestamp} seconds: {scene['description']}" if timestamp is not None else scene["description"])
    visible_text = analysis_data.get("visible_text")
    if isinstance(visible_text, list):
        readable_text = [str(item) for item in visible_text if isinstance(item, (str, int, float))]
        if readable_text:
            chunk_texts.append("Visible text: " + "; ".join(readable_text))

    for index, chunk_text in enumerate(chunk_texts):
        if not chunk_text.strip():
            continue
        db.add(ContentChunk(
            business_id=asset.business_id,
            asset_id=asset.id,
            source_type="asset_analysis",
            source_id=str(analysis.id),
            chunk_index=index,
            text=chunk_text,
        ))
    return analysis


def _claim_one_job(db: Session) -> UUID | None:
    now = utc_now()
    eligible = or_(
        (ProcessingJob.state == "pending") & or_(ProcessingJob.retry_at.is_(None), ProcessingJob.retry_at <= now),
        (ProcessingJob.state == "processing") & (ProcessingJob.retry_at <= now),
    )
    job = db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.job_type == JOB_TYPE, eligible)
        .order_by(ProcessingJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    logger.info("Jobs found in the database")
    if job is None:
        logger.error("No job found")
        return None

    asset = db.get(ContentAsset, job.asset_id) if job.asset_id else None
    logger.info("The content asset has been found and it is {}".format(asset))
    if asset is None:
        logger.info("no asset found")
        job.state = "failed"
        job.error_code = "asset_missing"
        job.completed_at = now
        db.commit()
        return job.id

    if job.attempt_count >= MAX_ATTEMPTS:
        job.state = "failed"
        job.error_code = "attempts_exhausted"
        job.completed_at = now
        asset.status = "failed"
        asset.processing_error = job.error_code
        db.commit()
        return job.id

    job.state = "processing"
    job.attempt_count += 1
    job.retry_at = now + timedelta(seconds=WORKER_LEASE_SECONDS)
    asset.status = "processing"
    asset.processing_error = None
    job_id = job.id
    db.commit()
    logger.info("found the job and processing it now.")
    return job_id


def process_one_video_job() -> bool:
    """Claim and process one job; return whether a queue item was claimed."""
    session_factory = get_session_factory()
    logger.info("got the session factory now... moving one to getting the job")
    with session_factory() as db:
        job_id = _claim_one_job(db)
        logger.info("Got the job now... the job id is {}".format(job_id))
    if job_id is None:
        logger.error("No job id is found")
        return False

    with session_factory() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.state != "processing":
            logger.info("No job found")
            return True
        asset = db.get(ContentAsset, job.asset_id) if job.asset_id else None
        logger.info(f"The content has been found and it asset class is {asset}")
        if asset is None:
            return True
        asset_id = asset.id

    try:
        with session_factory() as db:
            asset = db.get(ContentAsset, asset_id)
            if asset is None:
                raise FileNotFoundError("Video asset record is missing")
            logger.info("Analyzing video asset %s for job %s", asset_id, job_id)
            analyze_video(db, asset)
            asset.status = "ready"
            job = db.get(ProcessingJob, job_id)
            if job is None:
                raise RuntimeError("Processing job record disappeared")
            db.delete(job)
            db.commit()
            logger.info("Analyzed video asset %s and deleted processing job %s", asset_id, job_id)
    except Exception as exc:
        logger.exception("Video analysis failed for job %s", job_id)
        with session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            asset = db.get(ContentAsset, asset_id)
            if job is None:
                return True
            now = utc_now()
            error_code = "analysis_failed"
            job.error_code = error_code
            if job.attempt_count < MAX_ATTEMPTS:
                job.state = "pending"
                job.retry_at = now + timedelta(seconds=30 * (2 ** (job.attempt_count - 1)))
            else:
                job.state = "failed"
                job.retry_at = None
                job.completed_at = now
            if asset is not None:
                asset.status = "failed" if job.state == "failed" else "processing"
                asset.processing_error = error_code
            db.commit()
    return True


def run_worker() -> None:
    """Poll PostgreSQL continuously and process video jobs one at a time."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Video analysis worker started with local model at %s", get_settings().gemma_model_path)
    while True:
        try:
            if not process_one_video_job():
                logger.info("No job found in the database queue; sleeping for %s seconds", POLL_INTERVAL_SECONDS)
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Video analysis worker stopped")
            return
        except Exception:
            logger.exception("Worker iteration failed")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker()
