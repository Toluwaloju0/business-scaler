import os

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test_db")

from app.main import app

client = TestClient(app)


def test_business_profile_creation_and_fetch():
    payload = {
        "business_name": "Downtown Dental Studio",
        "niche": "Dental clinic",
        "location": "Chicago, IL",
        "service_offerings": "Teeth whitening, implants, family cleanings",
        "target_audience": "Busy families and professionals",
        "brand_tone": "Friendly and trustworthy",
        "posting_goals": "Generate more bookings and local awareness",
    }

    create_response = client.post("/api/v1/business-profiles/", json=payload)
    assert create_response.status_code == 200
    business = create_response.json()
    assert business["business_name"] == payload["business_name"]
    assert business["niche"] == payload["niche"]

    fetch_response = client.get(f"/api/v1/business-profiles/{business['id']}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["business_name"] == payload["business_name"]


def test_business_profile_post_returns_existing_profile_for_same_user():
    user_id = "test-user-profile-upsert"
    payload = {
        "user_id": user_id,
        "business_name": "Returning Customer Cafe",
        "niche": "Cafe",
        "location": "Seattle",
        "service_offerings": "Coffee and pastries",
        "target_audience": "Nearby residents",
        "brand_tone": "Warm",
        "posting_goals": "Increase morning visits",
    }

    first_response = client.post("/api/v1/business-profile", json=payload)
    second_response = client.post(
        "/api/v1/business-profile",
        json={**payload, "business_name": "Changed Name Should Not Replace Existing"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["id"] == second_response.json()["id"]
    assert second_response.json()["user_id"] == user_id
    assert second_response.json()["business_name"] == payload["business_name"]


def test_business_profile_post_creates_separate_profiles_for_different_users():
    payload = {
        "business_name": "Shared Name Studio",
        "niche": "Photography",
        "location": "Seattle",
        "service_offerings": "Portrait sessions",
        "target_audience": "Local families",
        "brand_tone": "Friendly",
        "posting_goals": "Book more sessions",
    }

    first = client.post(
        "/api/v1/business-profile", json={**payload, "user_id": "profile-owner-a"}
    ).json()
    second = client.post(
        "/api/v1/business-profile", json={**payload, "user_id": "profile-owner-b"}
    ).json()

    assert first["id"] != second["id"]
    assert first["user_id"] == "profile-owner-a"
    assert second["user_id"] == "profile-owner-b"


def test_social_account_connection_and_content_asset_upload():
    profile_payload = {
        "business_name": "CityFit Studio",
        "niche": "Gym and personal training",
        "location": "Austin, TX",
        "service_offerings": "Strength coaching, group classes, mobility sessions",
        "target_audience": "Busy professionals and beginners",
        "brand_tone": "Energetic and motivating",
        "posting_goals": "Increase memberships and class bookings",
    }

    profile_response = client.post("/api/v1/business-profiles/", json=profile_payload)
    profile_id = profile_response.json()["id"]

    account_response = client.post(
        f"/api/v1/business-profiles/{profile_id}/social-accounts",
        json={
            "platform": "instagram",
            "account_name": "cityfitstudio",
            "status": "connected",
            "access_token": "demo-token",
        },
    )
    assert account_response.status_code == 200
    assert account_response.json()["platform"] == "instagram"

    asset_response = client.post(
        f"/api/v1/business-profiles/{profile_id}/content-assets",
        json={
            "asset_type": "text",
            "title": "Morning mobility routine",
            "source_text": "New 15-minute mobility routine for busy professionals.",
        },
    )
    assert asset_response.status_code == 200
    asset = asset_response.json()
    assert asset["asset_type"] == "text"
    assert asset["business_profile_id"] == profile_id


def test_content_suggestions_generated_for_selected_platforms():
    profile_payload = {
        "business_name": "Sunset Spa",
        "niche": "Beauty and wellness spa",
        "location": "Miami, FL",
        "service_offerings": "Facials, massages, skin treatments, packages",
        "target_audience": "Women 25-45 interested in self-care",
        "brand_tone": "Calm and premium",
        "posting_goals": "Boost bookings and repeat visits",
    }

    profile_response = client.post("/api/v1/business-profiles/", json=profile_payload)
    profile_id = profile_response.json()["id"]

    client.post(
        f"/api/v1/business-profiles/{profile_id}/social-accounts",
        json={
            "platform": "instagram",
            "account_name": "sunsetspa",
            "status": "connected",
            "access_token": "demo-token",
        },
    )
    client.post(
        f"/api/v1/business-profiles/{profile_id}/content-assets",
        json={
            "asset_type": "text",
            "title": "Weekend self-care offer",
            "source_text": "Try a weekend facial package with a three-step glow ritual and free consultation.",
        },
    )

    suggestions = client.post(
        "/api/v1/content-suggestions/generate",
        json={"business_profile_id": profile_id, "platforms": ["instagram", "tiktok"]},
    )

    assert suggestions.status_code == 200
    body = suggestions.json()
    assert "platforms" in body
    assert len(body["platforms"]) >= 1
    assert body["platforms"][0]["suggestions"]


def test_phase_4_ranks_and_filters_assets_for_phase_5_generation():
    profile_response = client.post(
        "/api/v1/business-profiles/",
        json={
            "business_name": "Northside Dental",
            "niche": "Dental clinic",
            "location": "Chicago",
            "service_offerings": "Teeth whitening, cleanings",
            "target_audience": "Busy families",
            "brand_tone": "Friendly and clear",
            "posting_goals": "More dental appointments",
        },
    )
    profile_id = profile_response.json()["id"]

    relevant = client.post(
        f"/api/v1/business-profiles/{profile_id}/content-assets",
        json={
            "asset_type": "video",
            "title": "Dental cleaning for busy families",
            "source_text": "Our friendly dental team explains teeth cleanings for families.",
            "description": "A clear walkthrough of a family dental appointment.",
        },
    ).json()
    generic = client.post(
        f"/api/v1/business-profiles/{profile_id}/content-assets",
        json={"asset_type": "text", "title": "Notes", "source_text": "General update."},
    ).json()

    library = client.get(f"/api/v1/business-profiles/{profile_id}/content-assets")
    assert library.status_code == 200
    assert {item["id"] for item in library.json()} == {relevant["id"], generic["id"]}

    response = client.post(
        "/api/v1/content-suggestions/generate",
        json={
            "business_profile_id": profile_id,
            "platforms": ["instagram", "youtube"],
            "asset_ids": [relevant["id"]],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert [item["asset_id"] for item in result["selected_assets"]] == [relevant["id"]]
    assert result["trend_insight"]["format"] == "behind_scenes"
    assert result["trend_insight"]["live_trend_data_available"] is False
    assert len(result["platforms"]) == 2
    for platform in result["platforms"]:
        assert len(platform["suggestions"]) == 3
        assert all(draft["asset_ids"] == [relevant["id"]] for draft in platform["suggestions"])
        assert all(draft["on_screen_text"] and draft["sound_direction"] for draft in platform["suggestions"])
    assert result["platforms"][0]["suggestions"][0]["aspect_ratio"] == "9:16"
    assert result["platforms"][1]["suggestions"][0]["platform_format"] == "Short"


def test_phase_4_rejects_assets_from_another_profile():
    profile_payload = {
        "business_name": "Local Cafe",
        "niche": "Cafe",
        "location": "Portland",
        "service_offerings": "Coffee and pastries",
        "target_audience": "Nearby residents",
        "brand_tone": "Warm",
        "posting_goals": "Increase visits",
    }
    first_profile = client.post("/api/v1/business-profiles/", json=profile_payload).json()
    second_profile = client.post(
        "/api/v1/business-profiles/",
        json={**profile_payload, "business_name": "Riverside Cafe"},
    ).json()
    foreign_asset = client.post(
        f"/api/v1/business-profiles/{first_profile['id']}/content-assets",
        json={"asset_type": "text", "source_text": "Fresh coffee every morning."},
    ).json()

    response = client.post(
        "/api/v1/content-suggestions/generate",
        json={
            "business_profile_id": second_profile["id"],
            "platforms": ["instagram"],
            "asset_ids": [foreign_asset["id"]],
        },
    )

    assert response.status_code == 404


def test_phase_5_rejects_unknown_format_and_returns_three_drafts_without_assets():
    profile = client.post(
        "/api/v1/business-profiles/",
        json={
            "business_name": "Maple Salon",
            "niche": "Hair salon",
            "location": "Denver",
            "service_offerings": "Cuts and styling",
            "target_audience": "Local professionals",
            "brand_tone": "Confident",
            "posting_goals": "More bookings",
        },
    ).json()

    generated = client.post(
        "/api/v1/content-suggestions/generate",
        json={"business_profile_id": profile["id"], "platforms": ["tiktok"]},
    )
    invalid = client.post(
        "/api/v1/content-suggestions/generate",
        json={
            "business_profile_id": profile["id"],
            "platforms": ["tiktok"],
            "trend_format": "not-a-format",
        },
    )

    assert generated.status_code == 200
    assert generated.json()["selected_assets"] == []
    assert len(generated.json()["platforms"][0]["suggestions"]) == 3
    assert generated.json()["platforms"][0]["suggestions"][0]["platform_format"] == "Short video"
    assert invalid.status_code == 422


def test_media_upload_rejects_unsupported_file_type():
    profile_response = client.post(
        "/api/v1/business-profile",
        json={
            "user_id": "media-upload-user",
            "business_name": "Media Studio",
            "niche": "Photography",
            "location": "Seattle",
            "service_offerings": "Portraits",
            "target_audience": "Local families",
            "brand_tone": "Friendly",
            "posting_goals": "Book more sessions",
        },
    )
    profile_id = profile_response.json()["id"]

    response = client.post(
        f"/api/v1/business-profiles/{profile_id}/media-assets",
        files={"file": ("notes.txt", b"not media", "text/plain")},
    )

    assert response.status_code == 415


def test_database_settings_require_postgresql_url():
    import pytest

    from pydantic import ValidationError

    from app.settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="sqlite:///local.db")

    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://test:test@localhost/test_db",
    )
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")


def test_orm_metadata_includes_persistence_entities_and_password_free_sessions():
    from app.models import AuthSession, Base

    assert "users" in Base.metadata.tables
    assert "content_assets" in Base.metadata.tables
    assert "content_chunks" in Base.metadata.tables
    assert "post_performance_snapshots" in Base.metadata.tables
    assert {column.name for column in AuthSession.__table__.columns} == {
        "id",
        "user_id",
        "created_at",
        "expires_at",
        "revoked_at",
        "last_used_at",
        "device_label",
    }
