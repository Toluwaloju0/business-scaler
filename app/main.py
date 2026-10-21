from __future__ import annotations

import re
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_tables, get_db_session, test_database_connection
from app.models import Business, BusinessMembership, ContentAsset as ContentAssetModel, SocialAccount as SocialAccountModel, User
from app.media_processing import enqueue_video_analysis
from app.settings import get_settings

import logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    create_database_tables()
    yield

app = FastAPI(title="LocalBiz Social Growth App", version="0.1.0", lifespan=lifespan)

APK_FILE_PATH = Path(__file__).resolve().parent.parent / "frontend" / "builds" / "LocalBiz-preview.apk"


class BusinessProfileCreate(BaseModel):
    user_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    business_name: str = Field(..., min_length=2)
    niche: str = Field(..., min_length=2)
    location: str = Field(..., min_length=2)
    service_offerings: str = Field(..., min_length=2)
    target_audience: str = Field(..., min_length=2)
    brand_tone: str = Field(..., min_length=2)
    posting_goals: str = Field(..., min_length=2)


class BusinessProfile(BusinessProfileCreate):
    id: str
    user_id: str = Field(...)


class SocialAccountCreate(BaseModel):
    platform: str = Field(..., min_length=2)
    account_name: str = Field(..., min_length=2)
    status: str = "connected"
    access_token: Optional[str] = None


class SocialAccount(SocialAccountCreate):
    id: str
    business_profile_id: str
    access_token: None = None


class ContentAssetCreate(BaseModel):
    asset_type: str = Field(..., min_length=2)
    title: Optional[str] = None
    source_text: Optional[str] = None
    media_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    description: Optional[str] = None
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    storage_key: Optional[str] = None


class ContentAsset(ContentAssetCreate):
    id: str
    business_profile_id: str


class ContentSuggestionRequest(BaseModel):
    business_profile_id: str
    platforms: List[str] = Field(..., min_length=1)
    asset_ids: Optional[List[str]] = None
    trend_format: str = "auto"


TREND_FORMATS = {
    "before_after": {
        "label": "Before and after",
        "angles": ["The visible transformation", "The detail that changed everything", "The result, step by step"],
        "hooks": [
            "A small change can make a noticeable difference.",
            "Here is what focused care can help improve.",
            "See the process behind a more confident result.",
        ],
    },
    "educational_tip": {
        "label": "Quick educational tip",
        "angles": ["One useful tip", "A common question answered", "A simple step to try"],
        "hooks": [
            "A quick tip from your local {niche} team.",
            "Wondering where to start? Try this.",
            "Here is one thing to know before your next appointment.",
        ],
    },
    "behind_scenes": {
        "label": "Behind the scenes",
        "angles": ["A look at the process", "Meet the people behind the service", "A detail we never skip"],
        "hooks": [
            "Come behind the scenes at {business_name}.",
            "Here is how we prepare for a great customer experience.",
            "The care is in the details. Take a look.",
        ],
    },
    "customer_story": {
        "label": "Customer story",
        "angles": ["A customer's journey", "A question we hear often", "What a great experience looks like"],
        "hooks": [
            "Here is what customers often want to know about {service}.",
            "A good experience starts with listening.",
            "See how we make the process feel simpler.",
        ],
    },
    "offer_spotlight": {
        "label": "Offer spotlight",
        "angles": ["The offer at a glance", "Who this service is for", "What to expect when you book"],
        "hooks": [
            "Looking for {service}? Here is how to get started.",
            "A closer look at a service made for {audience}.",
            "Thinking about booking? Here is what to expect.",
        ],
    },
}

PLATFORM_SPECS = {
    "instagram": {"format": "Reel", "aspect_ratio": "9:16", "duration_seconds": "15-30"},
    "tiktok": {"format": "Short video", "aspect_ratio": "9:16", "duration_seconds": "15-30"},
    "snapchat": {"format": "Story", "aspect_ratio": "9:16", "duration_seconds": "5-15"},
    "youtube": {"format": "Short", "aspect_ratio": "9:16", "duration_seconds": "20-45"},
}

SUPPORTED_TREND_FORMATS = set(TREND_FORMATS)


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


def _rank_assets(profile: Dict[str, Any], assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    profile_context = " ".join(
        str(profile[field])
        for field in ("business_name", "niche", "service_offerings", "target_audience", "posting_goals")
    )
    profile_tokens = _tokens(profile_context)
    ranked: List[Dict[str, Any]] = []

    for asset in assets:
        asset_text = " ".join(
            str(asset.get(field) or "") for field in ("title", "source_text", "description")
        )
        asset_tokens = _tokens(asset_text)
        relevance = len(profile_tokens & asset_tokens) / max(len(profile_tokens), 1)
        completeness = sum(
            bool(asset.get(field)) for field in ("title", "source_text", "description", "media_url")
        ) / 4
        has_creative_material = bool(asset_text.strip() or asset.get("media_url"))
        score = round((0.60 * relevance + 0.30 * completeness + 0.10 * has_creative_material) * 100)
        reason = (
            "Relevant to the business profile and includes useful creative context."
            if relevance >= 0.15 and completeness >= 0.5
            else "Ranked using available profile relevance and asset details; add more context to improve the match."
        )
        ranked.append(
            {
                "asset_id": asset["id"],
                "title": asset.get("title") or "Untitled asset",
                "asset_type": asset["asset_type"],
                "score": score,
                "reason": reason,
            }
        )

    return sorted(ranked, key=lambda item: (-item["score"], item["title"].lower()))[:3]


def _choose_trend_format(requested: str, selected_assets: List[Dict[str, Any]]) -> str:
    if requested != "auto":
        if requested not in SUPPORTED_TREND_FORMATS:
            raise HTTPException(status_code=422, detail="Unsupported trend format")
        return requested

    asset_types = [asset["asset_type"] for asset in selected_assets]
    if "video" in asset_types:
        return "behind_scenes"
    if "image" in asset_types:
        return "before_after"
    if "text" in asset_types:
        return "educational_tip"
    return "educational_tip"


def _build_platform_suggestions(
    profile: Dict[str, Any], platform: str, trend_format: str, selected_assets: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    format_data = TREND_FORMATS[trend_format]
    platform_spec = PLATFORM_SPECS.get(
        platform,
        {"format": "Short video", "aspect_ratio": "9:16", "duration_seconds": "15-30"},
    )
    service = profile["service_offerings"].split(",")[0].strip()
    audience = profile["target_audience"]
    ctas = ["Save this for later", "Send us a message to learn more", "Book with our local team"]
    asset_ids = [asset["asset_id"] for asset in selected_assets]
    suggestions = []

    for index, angle in enumerate(format_data["angles"]):
        hook = format_data["hooks"][index].format(
            business_name=profile["business_name"],
            niche=profile["niche"],
            service=service,
            audience=audience,
        )
        suggestions.append(
            {
                "title": f"{format_data['label']}: {angle}",
                "format": format_data["label"],
                "hook": hook,
                "caption": (
                    f"{profile['business_name']} in {profile['location']} offers {profile['service_offerings']}. "
                    f"A friendly, {profile['brand_tone'].lower()} experience for {audience.lower()}."
                ),
                "cta": ctas[index],
                "on_screen_text": [hook, angle, ctas[index]],
                "aspect_ratio": platform_spec["aspect_ratio"],
                "duration_seconds": platform_spec["duration_seconds"],
                "platform_format": platform_spec["format"],
                "sound_direction": "Use an original voiceover or a sound licensed within the platform.",
                "asset_ids": asset_ids,
            }
        )

    return suggestions


def _profile_response(business: Business) -> BusinessProfile:
    return BusinessProfile(
        id=str(business.id),
        user_id=business.owner_user_id,
        business_name=business.name,
        niche=business.niche,
        location=business.location,
        service_offerings=business.service_offerings,
        target_audience=business.target_audience,
        brand_tone=business.brand_tone,
        posting_goals=business.posting_goals,
    )


def _asset_response(asset: ContentAssetModel) -> ContentAsset:
    return ContentAsset(
        id=str(asset.id),
        business_profile_id=str(asset.business_id),
        asset_type=asset.asset_type,
        title=asset.title,
        source_text=asset.source_text,
        media_url=None,
        file_name=asset.original_filename,
        file_size=asset.byte_size,
        description=asset.description,
        mime_type=asset.mime_type,
        sha256=asset.sha256,
        storage_key=asset.object_key,
    )


def _profile_uuid(profile_id: str) -> UUID:
    try:
        return UUID(profile_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Business profile not found") from None


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def readiness_check() -> Dict[str, str]:
    try:
        test_database_connection()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database is unavailable") from None
    return {"status": "ready", "database": "connected"}


@app.get("/download", response_class=HTMLResponse)
def apk_download_page() -> HTMLResponse:
        apk_available = APK_FILE_PATH.is_file()
        download_action = (
                '<a class="download" href="/download/LocalBiz.apk">Download Android APK</a>'
                if apk_available
                else '<span class="download disabled">APK build is not available yet</span>'
        )
        availability_message = (
                "The Android installer is ready to download. Open this page on your Android device and tap the button."
                if apk_available
                else "The download page is ready, but no APK has been built and placed on this server yet."
        )
        content = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#e4efe8">
    <title>LocalBiz Growth - Android app</title>
    <style>
        :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f2f6f3; color: #18392b; }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
        main {{ width: min(100%, 560px); background: #fff; border: 1px solid #dce6df; border-radius: 12px; padding: 32px; box-shadow: 0 18px 50px #18392b12; }}
        .mark {{ display: grid; place-items: center; width: 56px; height: 56px; border-radius: 14px; background: #27794f; color: white; font-weight: 800; font-size: 24px; }}
        h1 {{ margin: 22px 0 8px; font-size: 30px; }}
        p {{ color: #52675c; line-height: 1.6; }}
        .status {{ padding: 14px 16px; margin: 22px 0; border-radius: 8px; background: #eef4f0; color: #355442; }}
        .download {{ display: flex; justify-content: center; align-items: center; min-height: 52px; margin-top: 20px; border-radius: 8px; background: #27794f; color: white; font-weight: 700; text-decoration: none; }}
        .download.disabled {{ background: #dce6df; color: #52675c; cursor: not-allowed; }}
        .note {{ font-size: 13px; margin-top: 24px; }}
    </style>
</head>
<body>
    <main>
        <div class="mark" aria-hidden="true">L</div>
        <h1>LocalBiz Growth</h1>
        <p>Install the Android app to prepare local business content and upload media for your video ideas.</p>
        <div class="status">{availability_message}</div>
        {download_action}
        <p class="note">Android may ask you to allow installation from this browser. Only install this APK if you trust the source. The app connects to the LocalBiz backend at http://140.238.91.204.</p>
    </main>
</body>
</html>"""
        return HTMLResponse(content=content)


@app.get("/download/LocalBiz.apk", include_in_schema=False)
def download_android_apk() -> FileResponse:
        if not APK_FILE_PATH.is_file():
                raise HTTPException(status_code=404, detail="Android APK has not been built yet")
        return FileResponse(
                path=APK_FILE_PATH,
                media_type="application/vnd.android.package-archive",
                filename="LocalBiz-Growth.apk",
        )


@app.post("/api/v1/business-profile", response_model=BusinessProfile)
@app.post("/api/v1/business-profiles/", response_model=BusinessProfile, include_in_schema=False)
def create_business_profile(
    payload: BusinessProfileCreate,
    db: Session = Depends(get_db_session),
) -> BusinessProfile:
    user_id = payload.user_id or str(uuid4())
    existing_profile = db.scalar(select(Business).where(Business.owner_user_id == user_id))
    if existing_profile:
        return _profile_response(existing_profile)

    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id)
        db.add(user)

    business = Business(
        owner_user_id=user_id,
        name=payload.business_name,
        niche=payload.niche,
        location=payload.location,
        service_offerings=payload.service_offerings,
        target_audience=payload.target_audience,
        brand_tone=payload.brand_tone,
        posting_goals=payload.posting_goals,
    )
    db.add(business)
    try:
        db.flush()
        db.add(BusinessMembership(user_id=user_id, business_id=business.id, role="owner"))
        db.commit()
        db.refresh(business)
    except IntegrityError:
        db.rollback()
        concurrent_profile = db.scalar(select(Business).where(Business.owner_user_id == user_id))
        if concurrent_profile is None:
            raise HTTPException(status_code=409, detail="Could not create the business profile") from None
        return _profile_response(concurrent_profile)
    return _profile_response(business)


@app.get("/api/v1/business-profiles/{profile_id}", response_model=BusinessProfile)
def get_business_profile(profile_id: str, db: Session = Depends(get_db_session)) -> BusinessProfile:
    business = db.get(Business, _profile_uuid(profile_id))
    if business is None:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return _profile_response(business)


@app.post("/api/v1/business-profiles/{profile_id}/social-accounts", response_model=SocialAccount)
def create_social_account(
    profile_id: str,
    payload: SocialAccountCreate,
    db: Session = Depends(get_db_session),
) -> SocialAccount:
    business_id = _profile_uuid(profile_id)
    if db.get(Business, business_id) is None:
        raise HTTPException(status_code=404, detail="Business profile not found")

    account = db.scalar(
        select(SocialAccountModel).where(
            SocialAccountModel.business_id == business_id,
            SocialAccountModel.platform == payload.platform,
            SocialAccountModel.external_account_id == payload.account_name,
        )
    )
    if account is None:
        account = SocialAccountModel(
            business_id=business_id,
            platform=payload.platform,
            external_account_id=payload.account_name,
            account_name=payload.account_name,
            connection_state=payload.status,
            granted_scopes=[],
            token_ciphertext=None,
        )
        db.add(account)
    else:
        account.connection_state = payload.status

    db.commit()
    db.refresh(account)
    return SocialAccount(
        id=str(account.id),
        business_profile_id=str(account.business_id),
        platform=account.platform,
        account_name=account.account_name,
        status=account.connection_state,
        access_token=None,
    )


@app.get("/api/v1/business-profiles/{profile_id}/social-accounts", response_model=List[SocialAccount])
def list_social_accounts(profile_id: str, db: Session = Depends(get_db_session)) -> List[SocialAccount]:
    business_id = _profile_uuid(profile_id)
    if db.get(Business, business_id) is None:
        raise HTTPException(status_code=404, detail="Business profile not found")
    accounts = db.scalars(
        select(SocialAccountModel)
        .where(SocialAccountModel.business_id == business_id)
        .order_by(SocialAccountModel.created_at.desc())
    ).all()
    return [
        SocialAccount(
            id=str(account.id),
            business_profile_id=str(account.business_id),
            platform=account.platform,
            account_name=account.account_name,
            status=account.connection_state,
            access_token=None,
        )
        for account in accounts
    ]


@app.post("/api/v1/business-profiles/{profile_id}/content-assets", response_model=ContentAsset)
def create_content_asset(
    profile_id: str,
    payload: ContentAssetCreate,
    db: Session = Depends(get_db_session),
) -> ContentAsset:
    business_id = _profile_uuid(profile_id)
    if db.get(Business, business_id) is None:
        raise HTTPException(status_code=404, detail="Business profile not found")

    asset = ContentAssetModel(
        business_id=business_id,
        asset_type=payload.asset_type,
        title=payload.title,
        source_text=payload.source_text,
        description=payload.description,
        original_filename=payload.file_name,
        mime_type=payload.mime_type,
        byte_size=payload.file_size,
        sha256=payload.sha256,
        object_key=payload.storage_key,
        status="ready",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_response(asset)


@app.post(
    "/api/v1/business-profiles/{profile_id}/media-assets",
    response_model=ContentAsset,
)
async def upload_media_asset(
    profile_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
) -> ContentAsset:
    business_id = _profile_uuid(profile_id)
    if db.get(Business, business_id) is None:
        raise HTTPException(status_code=404, detail="Business profile not found")

    settings = get_settings()
    allowed_types = {
        "image/jpeg": ("image", ".jpg"),
        "image/png": ("image", ".png"),
        "image/webp": ("image", ".webp"),
        "video/mp4": ("video", ".mp4"),
        "video/quicktime": ("video", ".mov"),
        "video/webm": ("video", ".webm"),
    }
    media_type = (file.content_type or "").lower()
    if media_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Upload must be a JPEG, PNG, WebP, MP4, MOV, or WebM file")

    asset_type, extension = allowed_types[media_type]
    asset_id = str(uuid4())
    storage_key = f"{asset_id}{extension}"
    storage_dir = Path(settings.media_storage_dir).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    destination = storage_dir / storage_key
    total_size = 0
    checksum = sha256()
    logger.info("trying the upload now checking file size")

    try:
        with destination.open("wb") as destination_file:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > settings.max_upload_bytes:
                    print("file size exceeds {} \n raising 413 error now".format(settings.max_upload_bytes))
                    raise HTTPException(status_code=413, detail="File exceeds the configured upload size limit")
                checksum.update(chunk)
                destination_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    original_name = Path(file.filename or "upload").name[:255]
    asset = ContentAssetModel(
        id=UUID(asset_id),
        business_id=business_id,
        asset_type=asset_type,
        title=Path(original_name).stem or f"Business {asset_type}",
        original_filename=original_name,
        mime_type=media_type,
        byte_size=total_size,
        sha256=checksum.hexdigest(),
        object_key=storage_key,
        status="ready",
    )
    try:
        db.add(asset)
        if asset_type == "video":
            enqueue_video_analysis(db, asset)
        db.commit()
        db.refresh(asset)
        return _asset_response(asset)
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise


@app.get("/api/v1/business-profiles/{profile_id}/content-assets", response_model=List[ContentAsset])
def list_content_assets(profile_id: str, db: Session = Depends(get_db_session)) -> List[ContentAsset]:
    business_id = _profile_uuid(profile_id)
    if db.get(Business, business_id) is None:
        raise HTTPException(status_code=404, detail="Business profile not found")
    assets = db.scalars(
        select(ContentAssetModel)
        .where(ContentAssetModel.business_id == business_id)
        .order_by(ContentAssetModel.created_at.desc())
    ).all()
    return [_asset_response(asset) for asset in assets]


@app.post("/api/v1/content-suggestions/generate")
def generate_content_suggestions(
    payload: ContentSuggestionRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    business_id = _profile_uuid(payload.business_profile_id)
    business = db.get(Business, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="Business profile not found")

    profile = {
        "business_name": business.name,
        "niche": business.niche,
        "location": business.location,
        "service_offerings": business.service_offerings,
        "target_audience": business.target_audience,
        "brand_tone": business.brand_tone,
        "posting_goals": business.posting_goals,
    }
    asset_query = select(ContentAssetModel).where(ContentAssetModel.business_id == business_id)
    if payload.asset_ids is not None:
        try:
            requested_ids = {UUID(asset_id) for asset_id in payload.asset_ids}
        except ValueError:
            raise HTTPException(status_code=404, detail="One or more selected assets were not found")
        asset_query = asset_query.where(ContentAssetModel.id.in_(requested_ids))

    profile_assets = db.scalars(asset_query).all()
    if payload.asset_ids is not None and len(profile_assets) != len(set(payload.asset_ids)):
        raise HTTPException(status_code=404, detail="One or more selected assets were not found")

    asset_payloads = [
        {
            "id": str(asset.id),
            "asset_type": asset.asset_type,
            "title": asset.title,
            "source_text": asset.source_text,
            "description": asset.description,
            "media_url": asset.object_key,
        }
        for asset in profile_assets
    ]

    ranked_assets = _rank_assets(profile, asset_payloads)
    trend_format = _choose_trend_format(payload.trend_format, ranked_assets)
    platforms_payload = [
        {
            "platform": platform,
            "suggestions": _build_platform_suggestions(profile, platform, trend_format, ranked_assets),
        }
        for platform in payload.platforms
    ]

    return {
        "business_profile_id": str(business.id),
        "selected_assets": ranked_assets,
        "trend_insight": {
            "format": trend_format,
            "label": TREND_FORMATS[trend_format]["label"],
            "source": "profile and asset metadata heuristics",
            "live_trend_data_available": False,
        },
        "platforms": platforms_payload,
    }
