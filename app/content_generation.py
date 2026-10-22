"""Generate three content-library items from recent, completed media analyses."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.media_processing import _load_local_gemma, _model_input_device
from app.models import (
    AssetAnalysis,
    Business,
    ContentAsset,
    ContentChunk,
    ContentGenerationResult,
    GeneratedContent,
    ProcessingJob,
    utc_now,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)
ContentType = Literal["text", "image", "video"]
JOB_TYPE_PREFIX = "generate_content_"
MAX_JOB_ATTEMPTS = 3
JOB_LEASE_SECONDS = 60 * 60


def generate_content_items(
    *,
    content_type: ContentType,
    business_context: dict[str, str],
    analyses: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Use the local Gemma model to return exactly three title/body pairs."""
    type_guidance = {
        "text": "Write ready-to-publish social media post copy in the body.",
        "image": (
            "Write an image-generation brief in the body: describe the visible subject, setting, "
            "composition, lighting, brand feel, and any concise on-image wording. This is a brief; "
            "do not claim that an image has been generated."
        ),
        "video": (
            "Write a video-generation brief in the body: describe a short sequence of scenes, "
            "camera/action direction, optional voiceover or on-screen text, and an appropriate ending. "
            "This is a brief; do not claim that a video has been generated."
        ),
    }
    prompt = (
        "Create exactly three distinct social content ideas for this local business. Use only facts "
        "supported by the business profile and uploaded-media analyses. Do not invent prices, offers, "
        "customer testimonials, outcomes, or services. Make the writing fit the stated brand tone and "
        "audience. For every item, return a concise title and a useful body. "
        f"{type_guidance[content_type]} Return only valid JSON in this shape: "
        '{"items":[{"title":"...","body":"..."},{"title":"...","body":"..."},'
        '{"title":"...","body":"..."}]}.\n\n'
        "BUSINESS PROFILE:\n"
        f"{json.dumps(business_context, ensure_ascii=False)}\n\n"
        "LATEST COMPLETED UPLOAD ANALYSES (newest first; use all provided analyses):\n"
        f"{json.dumps(analyses, ensure_ascii=False)}"
    )

    processor, model = _load_local_gemma()
    import torch

    inputs = processor.apply_chat_template(
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        add_generation_prompt=True,
    ).to(_model_input_device(model))
    input_token_count = inputs["input_ids"].shape[-1]
    with torch.inference_mode():
        outputs = model.generate(**inputs, max_new_tokens=1200, do_sample=False)
    response = processor.decode(
        outputs[0][input_token_count:], skip_special_tokens=True
    ).strip()

    if response.startswith("```"):
        response = response.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        # Recover a JSON object if the model added a short preamble or suffix.
        start, end = response.find("{"), response.rfind("}")
        if start < 0 or end <= start:
            logger.warning("Gemma did not return a JSON object for content generation")
            raise RuntimeError("Gemma returned an invalid content response") from None
        try:
            parsed = json.loads(response[start : end + 1])
        except json.JSONDecodeError:
            raise RuntimeError("Gemma returned an invalid content response") from None

    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list) or len(items) != 3:
        raise RuntimeError("Gemma must return exactly three content items")

    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("Gemma returned a malformed content item")
        title, body = item.get("title"), item.get("body")
        if not isinstance(title, str) or not title.strip() or not isinstance(body, str) or not body.strip():
            raise RuntimeError("Gemma returned a content item without a title or body")
        normalized.append({"title": title.strip()[:240], "body": body.strip()})
    return normalized


def enqueue_content_generation(db: Session, business_id: UUID, content_type: ContentType) -> ProcessingJob:
    """Create a durable job; the API caller owns the transaction commit."""
    job = ProcessingJob(
        business_id=business_id,
        job_type=f"{JOB_TYPE_PREFIX}{content_type}",
        state="pending",
    )
    db.add(job)
    return job


def _claim_one_content_generation_job(db: Session) -> UUID | None:
    now = utc_now()
    eligible = or_(
        (ProcessingJob.state == "pending")
        & or_(ProcessingJob.retry_at.is_(None), ProcessingJob.retry_at <= now),
        (ProcessingJob.state == "processing") & (ProcessingJob.retry_at <= now),
    )
    job = db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.job_type.like(f"{JOB_TYPE_PREFIX}%"), eligible)
        .order_by(ProcessingJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    if job.attempt_count >= MAX_JOB_ATTEMPTS:
        job.state = "failed"
        job.error_code = "attempts_exhausted"
        job.completed_at = now
        db.commit()
        return None

    job.state = "processing"
    job.attempt_count += 1
    job.retry_at = now + timedelta(seconds=JOB_LEASE_SECONDS)
    job.error_code = None
    job.completed_at = None
    job_id = job.id
    db.commit()
    return job_id


def process_one_content_generation_job() -> bool:
    """Claim one generation job and save its results, keeping failures retryable."""
    session_factory = get_session_factory()
    with session_factory() as db:
        job_id = _claim_one_content_generation_job(db)
    if job_id is None:
        return False

    try:
        with session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.state != "processing":
                return True
            business = db.get(Business, job.business_id)
            if business is None:
                raise RuntimeError("Business profile for generation job no longer exists")

            content_type = job.job_type.removeprefix(JOB_TYPE_PREFIX)
            if content_type not in {"text", "image", "video"}:
                raise RuntimeError("Generation job has an unsupported content type")

            analyses = db.execute(
                select(AssetAnalysis, ContentAsset)
                .join(ContentAsset, AssetAnalysis.asset_id == ContentAsset.id)
                .where(
                    ContentAsset.business_id == business.id,
                    AssetAnalysis.status == "complete",
                )
                .order_by(AssetAnalysis.created_at.desc())
                .limit(5)
            ).all()
            if not analyses:
                raise RuntimeError("No completed upload analysis is available")

            analysis_context = [
                {
                    "analysis_id": str(analysis.id),
                    "asset_type": asset.asset_type,
                    "asset_title": asset.title or asset.original_filename or "Uploaded media",
                    "summary_and_scenes": analysis.extracted_text or "",
                    "tags": analysis.tags or [],
                }
                for analysis, asset in analyses
            ]
            business_context = {
                "business_name": business.name,
                "niche": business.niche,
                "location": business.location,
                "service_offerings": business.service_offerings,
                "target_audience": business.target_audience,
                "brand_tone": business.brand_tone,
                "posting_goals": business.posting_goals,
            }
            generated_items = generate_content_items(
                content_type=content_type,  # type: ignore[arg-type]
                business_context=business_context,
                analyses=analysis_context,
            )
            analysis_ids = [str(analysis.id) for analysis, _ in analyses]
            model_version = get_settings().gemma_model_path.rsplit("/", 1)[-1]
            generated_ids: list[str] = []
            for index, generated in enumerate(generated_items):
                item = GeneratedContent(
                    business_id=business.id,
                    content_type=content_type,
                    title=generated["title"],
                    body=generated["body"],
                    source_analysis_ids=analysis_ids,
                    model_version=model_version,
                )
                db.add(item)
                db.flush()
                generated_ids.append(str(item.id))
                db.add(ContentChunk(
                    business_id=business.id,
                    source_type="generated_content",
                    source_id=str(item.id),
                    chunk_index=index,
                    text=f"{item.title}\n{item.body}",
                ))

            db.add(ContentGenerationResult(
                job_id=job.id,
                business_id=business.id,
                content_type=content_type,
                generated_content_ids=generated_ids,
            ))
            job.state = "complete"
            job.retry_at = None
            job.error_code = None
            job.completed_at = utc_now()
            db.commit()
            logger.info("Generated %s %s items for job %s", len(generated_ids), content_type, job_id)
    except Exception:
        logger.exception("Content generation failed for job %s", job_id)
        with session_factory() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None:
                return True
            now = utc_now()
            job.error_code = "generation_failed"
            if job.attempt_count < MAX_JOB_ATTEMPTS:
                job.state = "pending"
                job.retry_at = now + timedelta(seconds=30 * (2 ** (job.attempt_count - 1)))
            else:
                job.state = "failed"
                job.retry_at = None
                job.completed_at = now
            db.commit()
    return True
