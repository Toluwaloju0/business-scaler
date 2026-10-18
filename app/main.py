from __future__ import annotations

import re
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.settings import get_settings

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    yield

app = FastAPI(title="LocalBiz Social Growth App", version="0.1.0", lifespan=lifespan)
app = FastAPI(title="LocalBiz Social Growth App", version="0.1.0")


business_profiles_db: Dict[str, Dict[str, Any]] = {}
social_accounts_db: Dict[str, Dict[str, Any]] = {}
content_assets_db: Dict[str, Dict[str, Any]] = {}


class BusinessProfileCreate(BaseModel):
    user_id: Optional[str] = Field(default=None, min_length=1)
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


class ContentAssetCreate(BaseModel):
    asset_type: str = Field(..., min_length=2)
    title: Optional[str] = None
    source_text: Optional[str] = None
    media_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    description: Optional[str] = None
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


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def readiness_check() -> Dict[str, str]:
    get_settings()
    return {"status": "configured"}


@app.post("/api/v1/business-profile", response_model=BusinessProfile)
@app.post("/api/v1/business-profiles/", response_model=BusinessProfile, include_in_schema=False)
def create_business_profile(payload: BusinessProfileCreate) -> BusinessProfile:
    user_id = payload.user_id or str(uuid4())
    existing_profile = next(
        (profile for profile in business_profiles_db.values() if profile["user_id"] == user_id),
        None,
    )
    if existing_profile:
        return BusinessProfile(**existing_profile)

    profile_id = str(uuid4())
    profile_data = payload.model_dump(exclude={"user_id"})
    profile = BusinessProfile(id=profile_id, user_id=user_id, **profile_data)
    business_profiles_db[profile_id] = profile.model_dump()
    return profile


@app.get("/api/v1/business-profiles/{profile_id}", response_model=BusinessProfile)
def get_business_profile(profile_id: str) -> BusinessProfile:
    profile = business_profiles_db.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return BusinessProfile(**profile)


@app.post("/api/v1/business-profiles/{profile_id}/social-accounts", response_model=SocialAccount)
def create_social_account(profile_id: str, payload: SocialAccountCreate) -> SocialAccount:
    if profile_id not in business_profiles_db:
        raise HTTPException(status_code=404, detail="Business profile not found")

    account_id = str(uuid4())
    account = SocialAccount(
        id=account_id,
        business_profile_id=profile_id,
        **payload.model_dump(),
    )
    social_accounts_db[account_id] = account.model_dump()
    return account


@app.post("/api/v1/business-profiles/{profile_id}/content-assets", response_model=ContentAsset)
def create_content_asset(profile_id: str, payload: ContentAssetCreate) -> ContentAsset:
    if profile_id not in business_profiles_db:
        raise HTTPException(status_code=404, detail="Business profile not found")

    asset_id = str(uuid4())
    asset = ContentAsset(
        id=asset_id,
        business_profile_id=profile_id,
        **payload.model_dump(),
    )
    content_assets_db[asset_id] = asset.model_dump()
    return asset


@app.post(
    "/api/v1/business-profiles/{profile_id}/media-assets",
    response_model=ContentAsset,
)
async def upload_media_asset(profile_id: str, file: UploadFile = File(...)) -> ContentAsset:
    if profile_id not in business_profiles_db:
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

    try:
        with destination.open("wb") as destination_file:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds the configured upload size limit")
                checksum.update(chunk)
                destination_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    original_name = Path(file.filename or "upload").name[:255]
    profile = business_profiles_db[profile_id]
    asset = ContentAsset(
        id=asset_id,
        business_profile_id=profile_id,
        asset_type=asset_type,
        title=Path(original_name).stem or f"{profile['business_name']} {asset_type}",
        file_name=original_name,
        file_size=total_size,
        media_url=None,
        storage_key=storage_key,
    )
    stored_asset = asset.model_dump()
    stored_asset["mime_type"] = media_type
    stored_asset["sha256"] = checksum.hexdigest()
    content_assets_db[asset_id] = stored_asset
    return asset


@app.get("/api/v1/business-profiles/{profile_id}/content-assets", response_model=List[ContentAsset])
def list_content_assets(profile_id: str) -> List[ContentAsset]:
    if profile_id not in business_profiles_db:
        raise HTTPException(status_code=404, detail="Business profile not found")
    return [
        ContentAsset(**asset)
        for asset in content_assets_db.values()
        if asset["business_profile_id"] == profile_id
    ]


@app.post("/api/v1/content-suggestions/generate")
def generate_content_suggestions(payload: ContentSuggestionRequest) -> Dict[str, Any]:
    if payload.business_profile_id not in business_profiles_db:
        raise HTTPException(status_code=404, detail="Business profile not found")

    profile = business_profiles_db[payload.business_profile_id]
    profile_assets = [
        asset
        for asset in content_assets_db.values()
        if asset["business_profile_id"] == payload.business_profile_id
    ]
    if payload.asset_ids is not None:
        requested_ids = set(payload.asset_ids)
        profile_asset_ids = {asset["id"] for asset in profile_assets}
        if not requested_ids.issubset(profile_asset_ids):
            raise HTTPException(status_code=404, detail="One or more selected assets were not found")
        profile_assets = [asset for asset in profile_assets if asset["id"] in requested_ids]

    ranked_assets = _rank_assets(profile, profile_assets)
    trend_format = _choose_trend_format(payload.trend_format, ranked_assets)
    platforms_payload = [
        {
            "platform": platform,
            "suggestions": _build_platform_suggestions(profile, platform, trend_format, ranked_assets),
        }
        for platform in payload.platforms
    ]

    return {
        "business_profile_id": payload.business_profile_id,
        "selected_assets": ranked_assets,
        "trend_insight": {
            "format": trend_format,
            "label": TREND_FORMATS[trend_format]["label"],
            "source": "profile and asset metadata heuristics",
            "live_trend_data_available": False,
        },
        "platforms": platforms_payload,
    }
