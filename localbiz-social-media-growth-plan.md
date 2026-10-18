# LocalBiz Social Media Growth App – Implementation Plan

## 1. Product vision

Build a mobile-first application for local businesses to turn their service offerings, visual assets, and text content into high-performing social posts across Instagram, TikTok, Snapchat, and YouTube. The app will:

- ingest videos, images, and text from the business owner or their team
- analyze each business and its audience context
- choose the best current content format using an open-weight AI model and trend-aware signals
- generate three content variations per platform for the user to review
- allow the user to pick the preferred post and schedule or auto-publish it
- track engagement, audience growth, and content effectiveness over time
- recommend better content strategies and alert the user when milestones are reached

The product should be mobile-friendly by design, usable on Android and iOS, and designed around a “draft-first, approve-second” publishing flow for safety and compliance.

---

## 2. Core requirements to satisfy

The implementation must cover the following end-to-end workflow:

1. Understand what is performing best for that day or week by using the LLM and trend intelligence signals.
2. Select the best files or text information to recreate or remix content similar to the strongest current trends.
3. Generate 3 content variations per social platform for the user’s selected audience and goals.
4. Allow automatic posting of the user-selected content version to the chosen platform.
5. Track and record follower growth, engagement, reach, clicks, and conversion signals per platform.
6. Suggest optimization options to improve future content quality.
7. Alert the user when important milestones are reached on each platform.
8. Keep the experience mobile-first and responsive across devices.

---

## 3. Product architecture overview

### High-level system

- Mobile app: cross-platform app for business operators to upload media, review AI-generated content, and approve posts
- Backend API: orchestrates AI jobs, media processing, platform publishing, analytics, and user account management
- AI/content pipeline: trend analysis, media scoring, content generation, remixing, and platform fit scoring
- Data layer: relational database for users and content records; object storage for media; cache for queued jobs and API responses
- Analytics engine: stores platform KPIs and measures content performance over time
- Scheduling and automation service: handles queueing, retries, approvals, and posting jobs

### Recommended app architecture

- Frontend: React Native + Expo
- Backend: FastAPI (Python)
- AI inference: Python + Hugging Face Transformers + vLLM or TGI
- Database: PostgreSQL
- Cache/queue: Redis + Celery or BullMQ
- Object storage: S3-compatible storage (AWS S3, Cloudflare R2, or DigitalOcean Spaces)
- Notifications: Phone status bar notifications on the user’s device (Android/iOS push or local notification channel).
- Analytics: PostHog or self-hosted analytics stack
- Monitoring: Sentry + OpenTelemetry

---

## 4. Recommended technology stack

### 4.1 Mobile application stack

- React Native + Expo
- Expo Router for navigation
- TypeScript
- NativeWind or Tamagui for design system
- Zustand for app state
- TanStack Query for async server state
- react-native-image-picker or Expo Image Picker
- react-native-video or Expo AV
- react-native-gesture-handler + reanimated
- Expo SecureStore for sensitive tokens
- Firebase Messaging / Expo Notifications for alerts

### 4.2 Backend / API stack

- FastAPI (Python) for the backend API and AI orchestration
- PostgreSQL
- SQLAlchemy + Alembic for data models and migrations
- Redis
- Celery for async jobs
- ffmpeg for video/transcoding and thumbnail generation
- OpenAPI/Swagger for API documentation
- JWT auth and refresh tokens

### 4.3 AI stack

- Python 3.11+
- Hugging Face Transformers
- Accelerate
- BitsAndBytes or AWQ/GPTQ for quantized inference if needed
- vLLM or Text Generation Inference (TGI) for serving models
- SentenceTransformers for embedding and similarity comparisons
- OpenCV and Pillow for image processing
- ffmpeg for video frame extraction and remixing
- Whisper or a similar model for speech-to-text if captions or voiceover extraction is required
- Hugging Face Hub for model management

### 4.4 Data and analytics stack

- PostgreSQL for persistent relational data
- Redis for quick access and task queueing
- S3 or R2 for media storage
- PostHog or a custom dashboard for KPI tracking
- Metabase for reporting if the app needs business-level dashboards
- ClickHouse or BigQuery is optional for scale if analytics become large

### 4.5 Integrations and platform APIs

- Instagram Graph API
- TikTok Content Posting APIs / Business APIs
- YouTube Data API / YouTube Studio API
- Snapchat Business API / content publishing integrations where supported
- Firebase Cloud Messaging for push alerts
- Google Analytics or platform native analytics if needed

---

## 5. Open-weight models to consider

The app should use an open-weight model stack rather than a closed commercial model. The recommended setup is a mix of a vision-language model for trend analysis and a text model for strategy generation, with a captioning or embedding model for content matching.

### Recommended model stack

1. Vision-language content scoring model
   - Qwen2.5-VL-7B-Instruct (Hugging Face)
   - Good choice for understanding uploaded visuals, extracting structure from images/videos, and ranking content concepts based on business context

2. Text strategy and recommendation model
   - Llama 3.1 8B Instruct or Mistral 7B Instruct
   - Good for converting business information, trends, and audience signals into structured content briefs and platform recommendations

3. Embedding / similarity model
   - sentence-transformers/all-MiniLM-L6-v2 or similar
   - Useful for matching business content to trending styles, concepts, and hook patterns without heavy compute

4. Optional OCR and caption extraction
   - TrOCR, PaddleOCR, or a similar OCR model for extracting text from screenshots, posters, and printed materials

5. Optional video understanding
   - A lightweight video-caption or video-frame summarization model if the product supports short-form video analysis

### How the LLM is used

The model should not simply “guess” what is trending. It should be fed structured inputs such as:

- business category and services
- posted content history and past engagement
- platform-specific audience behavior
- current trend patterns from public platform signals and internal analytics
- user content assets (photos, clips, text)
- successful content hooks from previous posts

Then the model scores candidate content formats such as:

- “before/after” transformation
- educational micro-tip
- testimonial story
- countdown or launch style
- process reveal
- UGC-style remix
- product close-up with hook + CTA

It returns a ranked list of formats and justifications. The app should surface those scores to the user and keep them editable.

---

## 6. End-to-end implementation flow

### Phase 1: User onboarding and business profile setup

- Capture business name, niche, location, services, tone, brand colors, target audience, and posting goals
- Ask the business what channels they want to grow: Instagram, TikTok, Snapchat, YouTube
- Connect the relevant social platform accounts with secure OAuth and permission scopes
- Store business assets and posting rules
- Define content constraints for each platform, including aspect ratio, caption length, CTA, and posting cadence

### Phase 2: Content input ingestion

- Allow image upload, video upload, PDF or text upload, and direct text entry
- Normalize and store original files in object storage
- Generate thumbnails, captions, metadata, and content tags for each asset
- Extract text from images using OCR when applicable
- Extract scenes or key frames from videos for AI review

### Phase 3: Trend and content intelligence layer

- Pull trend signals from recent platform engagement patterns and website/social references relevant to the business category
- Combine signals with the user’s own past post performance and prior audience feedback
- Use the LLM to interpret the content opportunity and identify the best format for the week/day
- Rank formats using a weighted score based on:
  - business relevance
  - trend momentum
  - audience fit
  - posting format compatibility
  - likely retention potential
  - conversion likelihood

Example scoring logic:

- format relevance to business service: 25%
- trend velocity: 20%
- platform fit: 20%
- user content suitability: 20%
- historical performance: 15%

### Phase 4: Best-asset selection and remix engine

- Evaluate uploaded media against selected trend formats
- Use embeddings and image similarity models to find the strongest hooks and assets
- Select the best images or clips based on:
  - quality
  - clear subject focus
  - brand alignment
  - emotional or educational value
  - platform requirements
- If the business has text only, generate scripts and hook lines from their services and offers
- Generate 3 content concepts per platform using the selected assets and trend insight

### Phase 5: Content generation

For each platform, create three different variations based on the same business idea, for example:

- Instagram Reel concept 1: before/after transformation
- Instagram Reel concept 2: quick customer testimonial + service proof
- Instagram Reel concept 3: educational tip carousel or voiceover reel

For TikTok:

- hook-first short-form video
- trending sound + service demonstration
- behind-the-scenes process reveal

For Snapchat:

- quick story sequence
- limited-time offer reveal
- mini tutorial or service CTA format

For YouTube:

- short-form YouTube Shorts version
- educational explainer
- local business authority clip

The app should:

- generate captions, hook lines, and CTA copy
- suggest on-screen text overlays
- set video aspect ratio and cut durations per platform
- propose background music or sound style if legally available and approved
- store all generated variations as drafts for review

### Phase 4–5 MVP implementation status

The current implementation provides a deterministic baseline for these phases:

- Source assets can be listed per business profile, explicistly selected, and ranked using profile-text overlap and available asset metadata.
- The generation request can choose one of the supported creative formats or select a starting format from the selected asset types.
- Exactly three draft variations are returned per requested platform, including a hook, caption, CTA, on-screen text, aspect ratio, duration guidance, and platform format.
- Each draft records the selected asset IDs it was based on. The response identifies the ranking source and explicitly reports that live trend data is not connected.

This is not yet production trend intelligence or multimodal AI: the ranking does not inspect image/video pixels, calculate embeddings, read platform trend feeds, or use historical engagement. Platform publishing, scheduling, and approval are intentionally out of scope here and remain in later phases. The outputs are drafts and must be reviewed by the business before publication.

## Testing and validation for Phase 1 and Phase 2

The first two phases are the foundation of the product, so they must be validated with both technical and business-facing checks.

### Phase 1 validation: onboarding and business profile setup

#### Functional tests

- User can create an account and log in successfully.
- User can complete a business profile form with name, niche, location, services, audience, tone, and goals.
- Business profile data persists correctly in the database.
- Selected social platforms are stored and linked to the correct user account.
- OAuth connection for each platform succeeds and stores only necessary permissions.
- Errors are handled correctly when a platform connection fails or an access token expires.
- User sees a clear validation message when required fields are missing.
- Profile edits update the backend and reflect in the mobile app immediately.

#### Acceptance criteria

- A business profile is complete enough to generate relevant content recommendations.
- A user can onboard in under 5 minutes without confusion.
- Platform accounts are connected securely and stored encrypted.
- Each platform selection is reflected in the content generation workflow.

#### Example test cases

1. Create business profile with valid data and confirm it is saved.
2. Submit incomplete form and confirm validation error appears.
3. Connect Instagram account and confirm permission scopes are stored correctly.
4. Disconnect a platform and ensure the app no longer tries to publish to it.
5. Attempt OAuth error scenario and confirm the user receives a readable failure message.

### Phase 2 validation: content input ingestion

#### Functional tests

- User can upload an image, video, PDF, or text snippet.
- Uploaded media is stored in object storage and a database record is created.
- File metadata is correct: file type, size, owner ID, upload timestamp, and platform references.
- OCR extracts text from uploaded images or documents when enabled.
- Video frame extraction produces representative thumbnail or scene data.
- Text-only input is accepted and stored correctly.
- Duplicate or invalid files are rejected with a proper error message.
- Insufficient internet or a failed upload does not leave incomplete records in the database.

#### Acceptance criteria

- Every uploaded asset is traceable to a user and business profile.
- Content can be ingested in multiple formats and normalized for the AI stage.
- The app stores enough metadata to allow content ranking, remixing, and later publishing.

#### Example test cases

1. Upload a valid image and confirm it is stored and linked to the business profile.
2. Upload a valid short video and confirm thumbnails and metadata are generated.
3. Upload an unsupported file type and confirm rejection.
4. Upload a large video and confirm it is compressed or queued for background processing.
5. Enter text only and confirm the app creates a content record without media file attachments.
6. Run OCR on a poster image and confirm extracted text is available in the backend response.
7. Simulate a storage failure and confirm the user sees a retry/error message and no corrupted record remains.

### Test plan summary

Use the following test mix:

- Unit tests for profile validation and upload validation rules
- Integration tests for API endpoints and database writes
- Mobile UI tests for onboarding flow and upload success/failure states
- End-to-end tests for creating a business profile and uploading assets

### Exit criteria for Phase 1 and Phase 2

Phase 1 is complete when a user can fully onboard and create a valid business profile linked to one or more platform accounts.

Phase 2 is complete when the system can reliably accept, store, process, and tag media or text input for future AI content generation without data loss or broken uploads.

### Phase 6: Review and approval workflow

- User sees 3 generated concepts for each intended platform
- User can choose one recommended option or adjust prompts manually
- Provide approval checkpoints before posting
- Support “schedule”, “publish now”, or “save as draft” flows
- Keep a human-in-the-loop approval process by default

### Phase 7: Automated posting and scheduling

- Once approved, the system schedules or publishes the post via the corresponding platform API
- Adhere to each platform’s API rules, rate limits, and content restrictions
- Securely store access tokens in encrypted storage
- Retry failed posts with backoff and status tracking
- Log all actions to an audit table for transparency

### Phase 8: Growth tracking and analytics

Capture KPIs per platform after publication:

- follower growth
- reach and impressions
- video retention or watch time
- click-through rate
- saves, shares, comments, and likes
- profile visits
- conversion to leads or bookings

Use these metrics to:

- measure which content formats perform best
- identify when a content category has reached a milestone
- suggest improvements for subsequent content

### Phase 9: Optimization and recommendations

The AI should suggest next actions such as:

- post more “before/after” content if that performs best
- switch CTA wording for stronger conversions
- increase frequency of service-specific educational clips
- adjust posting time based on engagement history
- propose a higher-performing caption style or topic angle

### Phase 10: Milestone alerts

The system should track thresholds such as:

- 100 new followers in a week
- 10% engagement increase month-over-month
- 50 profile visits from one post
- 5 lead inquiries via a CTA or DM campaign
- consistent reach above a target baseline

The app sends alerts via push notifications or in-app banners when milestones are hit.

---

## 7. Technical workflow steps for implementation

1. Define the user data model and business profile schema.
2. Build the mobile UX for media upload, brief generation, and content review.
3. Set up server-side API routes for auth, storage, trend analysis, and post generation.
4. Build media preprocessing pipeline for uploads and platform format normalization.
5. Integrate a vision-language model for content scoring and strategy recommendation.
6. Add retrieval and embedding layer for matching prior posts and trend formats.
7. Implement the content generation service for 3 variations per platform.
8. Add review and approval flow with scheduler and publish queue.
9. Connect platform APIs securely and add error handling.
10. Add analytics ingestion and dashboards for growth tracking.
11. Add milestone alerting and recommendation engine.
12. Run pilot tests with real businesses and iterate on conversion quality.

---

## 8. Step-by-step success plan

### Step 1: Validate the core problem

- Interview 10–20 local businesses
- Confirm their biggest content pain points and posting routines
- Identify the most common service verticals: restaurants, salons, gyms, real-estate teams, clinics, dentists, auto shops, etc.

### Step 2: Build MVP with one platform

- Start with Instagram or TikTok
- Support image and short-form video input
- Generate 3 versions of a post
- Allow review and single-platform posting
- Collect performance metrics

### Step 3: Add analytics and learning loop

- Measure engagement and follower growth for each content type
- Feed performance back into the model ranking logic
- Improve generation quality for relevant verticals

### Step 4: Expand to all four platforms

- Add platform-specific templates and compliance rules
- Tune output by aspect ratio, duration, caption length, and CTA style
- Build schedule and multi-platform support

### Step 5: Launch business dashboard and optimization layer

- Add ROI dashboard and milestone tracking
- Provide weekly growth summary and content suggestions
- Introduce intelligence reports for each business

### Step 6: Scale and harden

- Improve webhook handling and reliability
- Add deeper moderation and approval flows
- Add enterprise-grade logging, rate limiting, and security controls

---

## 9. Constraints and product guardrails the user must know

### 9.1 Platform restrictions and policy limits

- Not every platform allows full automated publishing for every business account type.
- Instagram, TikTok, Snapchat, and YouTube all have API and account verification constraints, content policies, and rate limits.
- Auto-posting should only work after the user grants explicit OAuth permissions and the app obtains the appropriate API access.
- Content must comply with each platform’s terms of service, including restrictions on copyrighted music, trademarked assets, spammy repetition, and manipulated engagement.

### 9.2 AI and content quality constraints

- The LLM should be treated as a recommendation engine, not a guaranteed performance oracle.
- Trend-based recommendations must be grounded in recent platform and business data, not just general knowledge.
- The model should not assume a “best” format without considering business context, audience fit, and content quality.
- AI-generated materials should be reviewed before posting to avoid poor brand fit, off-brand language, or inappropriate tactics.

### 9.3 Legal and compliance constraints

- Businesses must have the right to use uploaded media and any associated text before the app uses it for generation or publication.
- The app should not use copyrighted music, logos, or branded content without permission.
- Any generated content that mentions claims, health results, legal outcomes, or pricing should be reviewed by the business owner.
- If the app supports customer testimonials, the user must confirm the testimonial is real, accurate, and authorized.

### 9.4 Privacy and security constraints

- User tokens and API credentials must be encrypted at rest and never stored in plaintext.
- Media should be stored securely and access-controlled by business and account.
- The app should follow least-privilege permissions for all third-party integrations.
- The system must be careful about sharing business analytics with unauthorized users or employees.

### 9.5 Mobile constraints

- The app must be optimized for lower bandwidth, smaller screens, and slower mobile networks.
- Video uploads should be compressed or queued for background processing.
- Background publishing should respect platform and mobile OS limitations, especially on iOS and Android.
- Push notifications must be concise and relevant to avoid notification fatigue.

### 9.6 Safety and moderation constraints

- The app must include a “safe by default” moderation layer for explicit, discriminatory, misleading, or unsafe content.
- Auto-publishing should default to “draft and approve,” not direct publish, unless the user explicitly opts into full automation.
- The app should flag posts with low brand fit or user-risk concerns.
- If a platform rejects content, the system should log the rejection reason and suggest a safe variation.

### 9.7 Performance and reliability constraints

- The AI generation workflow should return content quickly enough to feel native to mobile users, typically under a few minutes for short-form variations.
- Background jobs should be queued and retriable to handle API rate limits and temporary third-party failures.
- The app should support offline editing, local drafts, and resynchronization when network is restored.

### 9.8 Business and product constraints

- Not all businesses have the same content maturity; the product should support low-volume, low-skill users and more advanced users.
- Automating posts is valuable, but over-automation can damage trust. Human approval should remain available and customizable.
- The app should focus on usable, verified systems first; “best trend prediction” is only useful if it produces safer, more compelling public content.

---

## 10. Recommended MVP definition

The first release should include:

- business profile and platform account connection
- media upload and text intake
- AI-generated strategy and format ranking
- 3 content variations per selected platform
- review and approval workflow
- scheduling and platform publishing for one or two platforms only
- analytics for engagement and follower growth
- milestone alerts and weekly summaries

This MVP should be narrow enough to validate demand and strong enough to generate a real business outcome.

---

## 11. Recommended implementation sequence

1. Build the mobile app shell and business profile flow.
2. Build secure auth and platform connection layer.
3. Create media ingestion and preprocessing pipeline.
4. Implement trend intelligence and format scoring model.
5. Build AI content generation engine for 3 variations per platform.
6. Add user review and scheduling logic.
7. Connect publishing APIs and add retries/observability.
8. Implement analytics and milestone notifications.
9. Add recommendation engine and weekly business insights.
10. Pilot with a few local businesses and iterate.

---

## 12. Final recommendation

The best way to deliver this product successfully is to treat it as an AI-assisted marketing operating system for local businesses, not just a content generator. The critical success factors are:

- clear business context
- safe and explicit platform integration
- strong human review flow
- trend analysis grounded in real data
- reliable content tracking and growth measurement
- mobile-first usability

If implemented in this order, the app will be useful quickly, while still leaving room for advanced automation and analytics later.

---

## 13. Phase 2 database and persistence implementation plan

### 13.1 Goals and boundaries

Phase 2 persistence must replace the current process-local dictionaries without changing the existing API's business workflow. A restart must not lose users, businesses, profiles, uploaded text, asset metadata, generated drafts, sessions, or analytics. Uploaded binary media belongs in private object storage; PostgreSQL stores its ownership, object key, metadata, processing state, extracted text, and references. Do not store large image/video/PDF binaries in PostgreSQL.

The database URL is required configuration, not an optional fallback. The backend must load it from the process environment or project `.env`, validate it before serving requests, and stop startup with a clear configuration error if it is absent, blank, malformed, or has an unsupported scheme. Never print the URL or its credentials in logs.

### 13.2 Initial technology and configuration decisions

- PostgreSQL is the system of record; use SQLAlchemy 2.x ORM with synchronous sessions initially because the current FastAPI route handlers are synchronous. Use Alembic for all schema changes; do not use `create_all()` as a production migration strategy.
- Use a PostgreSQL driver supported by the selected SQLAlchemy version. Normalize accepted URL schemes in one settings module, and keep connection construction out of route handlers.
- Load settings through a typed settings class that reads `.env` and real environment variables, with real environment variables taking precedence. Make the URL field required and validate PostgreSQL scheme/driver and non-whitespace value. Fail fast during application startup and provide a separate database readiness check that does not expose credentials.
- Commit `.env.example` with variable names and safe placeholders only. Add `.env`, local database files, and test secrets to `.gitignore`; never commit real credentials. Use separate development, test, staging, and production databases.
- Use PostgreSQL `pgvector` for embeddings in the initial RAG implementation so relational tenant filters and vector retrieval share one authorization boundary. Keep the embedding provider/model and vector size recorded with each embedding so the model can be changed through a deliberate re-embedding migration.
- Use an S3-compatible private object store for binary uploads. Store bucket/object key and checksums in PostgreSQL; keep credentials in the same environment/secret-manager configuration, not in the database or mobile bundle.

### 13.3 ORM entities and relationships

All user-owned rows must include or be reachable through an immutable owner/business relationship. Add database foreign keys, uniqueness constraints, indexes, timestamps, and deletion behavior explicitly. Use UUID primary keys for public entities; avoid exposing sequential database IDs.

| Entity | Purpose and important fields |
| --- | --- |
| `User` | `id` (the stable `user_id` referenced by profiles and sessions), `display_name`, `is_active`, timestamps. This user-reference model does not contain a password or password hash. |
| `Business` | `id`, `name`, niche, location, services, target audience, tone, goals, brand settings, timestamps. This replaces the business profile record as durable data. |
| `BusinessMembership` | `user_id`, `business_id`, role, invited/accepted timestamps; unique pair. Enables team access while keeping authorization business-scoped. |
| `AuthSession` | `id`, `user_id` foreign key, created/expiry/revocation timestamps, optional non-sensitive device metadata. The session references the user by `user_id` and contains no password or `password_hash`; credentials are not profile/session fields. |
| `SocialAccount` | `business_id`, platform, external account ID/name, granted scopes, connection state, token ciphertext/reference, token expiry. Unique platform/account per business; never return credentials from API responses. |
| `ContentAsset` | `id`, `business_id`, creator user, kind, title, source text, description, original filename, validated MIME type, byte size, SHA-256 checksum, private object key, status, error, upload timestamp. Text-only records may have no object key. |
| `AssetDerivative` | `asset_id`, derivative kind, private object key, MIME type, dimensions/duration, checksum, processing status. Stores thumbnails, normalized media, and extracted frames separately from originals. |
| `AssetAnalysis` | `asset_id`, processor/model version, extracted text/OCR/transcript, tags, quality/subject scores, analysis state, timestamps. Preserve provenance and permit reprocessing. |
| `ContentChunk` | `business_id`, optional `asset_id` or `draft_id`, ordinal, text, source metadata, embedding model/version, vector. Chunks always carry business scope for filtered retrieval. |
| `GeneratedDraft` | `id`, `business_id`, creator, platform, selected asset references, creative format, hook, caption, CTA, overlays, production specs, status, generation/model version, timestamps. Draft remains distinct from a published post. |
| `ContentRating` | `business_id`, `draft_id`/published content reference, user, rating, optional reason, created/updated timestamps. One explicit rating per user and content item; supports user feedback without treating popularity as quality. |
| `PublishedPost` | `business_id`, social account, source draft, external post ID, platform, publish state/timestamps, request/idempotency key, failure code/message. |
| `PostPerformanceSnapshot` | `published_post_id`, captured time, impressions/reach/views/likes/comments/shares/saves/clicks/conversions/followers as nullable counters, platform, raw-source version. Use snapshots to calculate rates over time rather than overwrite history. |
| `ProcessingJob` | `business_id`, optional `asset_id`, job type, state, attempt count, retry time, safe error code, started/completed timestamps. Makes extraction and embedding work resumable and idempotent. |
| `AuditEvent` | actor, business, action, subject, timestamp, request correlation ID, non-sensitive metadata. Never include access tokens, passwords, or uploaded content bodies. |

For asset-to-draft and draft-to-published relationships, use explicit association tables where one draft can cite several assets or a post can be derived from several drafts. Add indexes for owner/business foreign keys, status, created time, expiry, platform/external ID, and common filtered retrieval columns.

### 13.4 Session authentication and authorization

1. The current Phase 2 identity flow uses a stable `user_id` generated once by the client and persisted locally; the backend profile endpoint accepts it and associates the generated profile with it. No password or password hash is part of the profile or session payload.
2. The session record references its user only through `user_id`; lifecycle timestamps and non-sensitive device metadata may be stored separately. Never put password material in a session record.
3. `POST /api/v1/business-profile` checks for an existing profile by `user_id`. If found, it returns that stored profile unchanged; otherwise it creates a new profile and returns the generated profile ID plus `user_id`. Keep `POST /api/v1/business-profiles/` as a compatibility alias during migration.
4. Business-scoped routes resolve records through the returned profile ID and, once membership authorization is implemented, verify that the active session's `user_id` owns or belongs to that profile. Use 404 for inaccessible resources where that avoids leaking resource existence.
5. A client-generated `user_id` is an identifier, not proof of identity: this no-password MVP upsert is not authentication and is vulnerable to spoofing if exposed publicly. Before production, bind `user_id` to a verified sign-in/session mechanism and enforce ownership server-side; keep any authentication credential separate from profile/session business fields.

### 13.5 Upload persistence and processing workflow

1. Authenticate and authorize the business before accepting an upload. Enforce allow-listed MIME types/extensions, maximum byte size, filename normalization, and per-business quota. Do not trust the client MIME type alone; verify file signatures where practical.
2. Create a pending `ContentAsset` record, compute/check SHA-256, and upload the original to a private object key that is not derived directly from the user filename. For direct-to-object-store mobile upload, issue a short-lived presigned upload URL and require a finalize call to verify size/checksum before marking the asset uploaded.
3. On any upload/storage failure, mark the record failed or remove the pending record and any partial object; retries must be safe and idempotent. Never leave an asset reported as ready when its object is missing.
4. Store text-only submissions as `ContentAsset.source_text`; treat OCR, PDF text, transcripts, video frames, thumbnails, and embeddings as asynchronous derivatives/analysis with explicit pending/ready/failed states.
5. Queue processing work using `ProcessingJob` and an outbox/transactional job record so database commits cannot silently lose work. Initial implementation may poll jobs without Redis; add Redis/Celery only when asynchronous processing is introduced.
6. Implement deletion as an authorized lifecycle: mark deletion requested, remove object and derivatives, then delete or tombstone database rows according to audit/retention requirements. Define retention and user export behavior before production.

### 13.6 RAG over highly rated content

- Index only content the current business is permitted to use: their uploaded notes, their own generated drafts, and their own published posts by default. Cross-business/global reuse is prohibited unless there is explicit opt-in, appropriate anonymization, and a documented rights basis.
- Build retrieval chunks from extracted asset text, approved drafts, and published post text. Attach `business_id`, source type/ID, platform, created/published time, consent/visibility state, embedding model/version, and chunk number to every chunk.
- Maintain explicit user ratings separately from observed post performance. Normalize engagement by available denominator (for example, engagement per reach or view) and compare within compatible platform/content format/time windows. Apply a minimum-volume threshold and Bayesian smoothing so tiny samples or one viral post do not dominate. Missing metrics remain unknown, not zero.
- Candidate retrieval first hard-filters by authenticated business, visibility/consent, platform compatibility, and eligible state; then performs vector similarity. Re-rank the small candidate set using semantic similarity, explicit quality rating, smoothed normalized performance, freshness, and content suitability. Store the ranking explanation and source IDs with the generation job for auditability.
- The generation prompt may use retrieved posts as examples of tone and effective structure, not as text to copy. Return source references with analysis so the app can show why examples were selected. Do not claim that a high historical score guarantees future performance.
- Test RAG isolation with two businesses containing near-identical queries and high-rated content; assert that no content, chunk, embedding, or citation from the other business is returned. Also test empty history, missing metrics, changed embedding versions, and stale/deleted source invalidation.

### 13.7 Delivery sequence

1. **Configuration gate:** add typed settings, `.env.example`, `.gitignore` safeguards, and tests proving `DATABASE_URL` is loaded from `.env`, overridden by the real environment, rejected when missing/blank/unsupported, and never logged.
2. **Database foundation:** add SQLAlchemy engine/session lifecycle, request-scoped unit-of-work dependency, health/readiness checks, Alembic, first migration, and disposable PostgreSQL test configuration. App startup must fail clearly when configuration is absent or the database cannot be reached.
3. **Identity and session:** implement User, Business, BusinessMembership, and AuthSession ORM models/repositories with sessions referencing users by `user_id` and no password/password-hash fields in session data; add profile lookup-or-create by user ID and authorization tests. Add a verified authentication mechanism before public production use. Preserve the legacy plural profile path as a compatibility alias.
4. **Asset persistence:** implement ContentAsset/AssetDerivative/AssetAnalysis/ProcessingJob records and private storage adapter. Persist text assets first; add image/video/PDF upload, finalize, metadata validation, checksum, failure cleanup, and retry behavior.
5. **Draft and performance history:** persist generated drafts, ratings, published-post references, and append-only performance snapshots. Keep external publishing disabled until authenticated consent and phase-6 review controls exist.
6. **Retrieval foundation:** install/enable pgvector, persist versioned embeddings and chunks, add business-filtered top-k retrieval, relevance/rating/performance reranking, source attribution, and cross-tenant tests. Start with seeded fixtures and explicit ratings; introduce live engagement inputs only when available.
7. **Cutover and verification:** move current in-memory profile/account/asset endpoints to database-backed repositories without changing response fields unnecessarily; run migrations on a fresh test database; verify restart persistence, backup/restore, and no secrets in logs before using a non-test database.

### 13.8 Phase 2 testing and exit criteria

**Configuration and schema tests**

- Startup rejects absent, whitespace-only, malformed, and unsupported `DATABASE_URL`; accepts a valid PostgreSQL URL loaded from `.env`; process environment overrides `.env`.
- Alembic can build a fresh database to head and upgrade a previous supported schema. Migration tests run against PostgreSQL, not SQLite, for PostgreSQL types/extensions and constraint behavior.
- All owner relationships, uniqueness rules, delete behavior, and indexes are verified at the database boundary.

**Identity and isolation tests**

- Repeated profile POSTs for the same `user_id` return the same profile; a different `user_id` cannot resolve that profile. Session lifecycle and ownership tests must confirm there are no password/password-hash fields in session records.
- A user cannot list, retrieve, modify, upload to, or retrieve RAG context from another business without membership; forged owner IDs are ignored.
- Social credentials are encrypted or stored by a secret reference and are never returned in API responses or written to logs.

**Phase 2 upload tests**

- Valid text and allowed image/video/PDF uploads produce durable records; binary bytes are in object storage and the matching private object key/checksum/size is in the database.
- Unsupported format, mismatched MIME/signature, excessive size/quota, duplicate checksum, missing object, storage timeout, and interrupted upload produce an understandable error and no ready-but-broken asset.
- OCR/transcript/extraction job retries are idempotent; processing status and failure are visible; deleting an asset removes or invalidates its derivatives/chunks.
- Restart the API between write and read operations and confirm the profile, memberships, asset metadata, and text content persist.

**Phase 2 exit criteria**

- App startup demonstrably refuses to run without a loaded, valid database URL.
- A user can authenticate, create a business, upload text and a media file, restart the API, and retrieve only their authorized records.
- Media is private and retrievable only through authorized, time-limited access; upload failure cleanup is covered by integration tests.
- RAG may remain behind a feature flag until embeddings are available, but schema, tenant filters, explicit rating/performance signals, source attribution, and isolation tests are in place before enabling it.

### 13.9 Risks and decisions to settle before implementation

- **Credential handling:** determine password-only, email-link, or third-party sign-in policy and account recovery before exposing registration publicly.
- **Object storage:** select the actual S3-compatible provider and define private bucket CORS, encryption, lifecycle, maximum upload size, and backup policy. Do not put object-store secrets in Expo public variables.
- **RAG data rights:** decide whether ratings and retrieval are business-private only; default to private per business. Do not train a shared/global corpus from customer data without explicit consent.
- **Engagement comparability:** platform metrics and denominators differ; document normalization, minimum sample size, time windows, and how missing/private platform metrics are handled.
- **Database and test services:** local development and CI need a disposable PostgreSQL instance with the same extensions as production; tests must never use a developer's or production database.
- **Current local profile cache:** keep AsyncStorage limited to non-secret offline form convenience. Once authenticated sync is implemented, reconcile local drafts by stable client-generated IDs and show pending/synced/failed states rather than treating the cache as the source of truth.

### 13.10 Initial implementation status

The first database and media-upload foundation has now been added to the repository:

- `app/settings.py` loads `DATABASE_URL` from `.env`/the environment, rejects missing, blank, malformed, and non-PostgreSQL URLs, and keeps the value secret when represented in settings.
- `app/database.py` creates SQLAlchemy engine/session dependencies lazily; importing the app does not establish a database connection.
- `app/models.py` defines UUID-backed ORM metadata for users, businesses, memberships, user-ID-only sessions, social accounts, content assets and derivatives/analysis, drafts, draft-asset links, ratings, published posts, performance snapshots, vector chunks, processing jobs, and audit events. Session columns contain no password or password hash.
- `.env.example` is a template only and must be copied/configured with a real PostgreSQL URL by the developer. The checked-out workspace had no `.env` or `DATABASE_URL`; no working database credential has been fabricated.
- Alembic configuration and an environment scaffold are present. A real first schema revision and `pgvector` extension creation still require a configured disposable PostgreSQL instance.
- `GET /ready` verifies that the required configuration loads without returning the database URL.
- The frontend now has a bottom navigation entry and a media page using Expo ImagePicker for multiple image/video selections. The FastAPI media endpoint validates an allow-listed MIME type and configured byte limit, computes SHA-256, uses a generated filename, and saves to the configured local media directory.

**Important current boundary:** the legacy profile, social-account, and content-asset APIs still use process-local dictionaries; the new ORM models are not yet connected to those routes, and Alembic migrations have not been generated/applied. The media upload endpoint currently writes files to local disk and its metadata to the in-memory asset dictionary; it is development-only, not durable database/object-store persistence. The app refuses startup without a valid `.env`/environment URL, and this workspace requires the developer to configure that URL before running Uvicorn. Model inference/asset analysis is not yet implemented: uploads are available as future model inputs, but the screen does not claim the open-weight model has analyzed them yet.
