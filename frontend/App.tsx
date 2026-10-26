import React, { useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { StatusBar } from 'expo-status-bar';
import {
  Alert,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as FileSystem from 'expo-file-system/legacy';
import { Image } from 'react-native';

type PlatformKey = 'instagram' | 'tiktok' | 'snapchat' | 'youtube';

type BusinessProfileForm = {
  business_name: string;
  niche: string;
  location: string;
  service_offerings: string;
  target_audience: string;
  brand_tone: string;
  posting_goals: string;
};

type ContentAssetForm = {
  asset_type: 'image' | 'video' | 'text';
  title: string;
  source_text: string;
  description: string;
};

type ContentAssetRecord = {
  id: string;
  asset_type: 'image' | 'video' | 'text';
  title: string | null;
  source_text: string | null;
  description: string | null;
  content_generation_status: 'pending content generation' | 'processing content generation' | 'completed content generation';
};

type GeneratedContentType = 'text' | 'image' | 'video';

type GeneratedContentRecord = {
  id: string;
  business_profile_id: string;
  content_type: GeneratedContentType;
  title: string;
  body: string;
  source_analysis_ids: string[];
  created_at: string;
};

type ContentGenerationJobRecord = {
  job_id: string;
  status: 'pending' | 'processing' | 'complete' | 'failed';
  content_type: GeneratedContentType;
  items: GeneratedContentRecord[];
  error_message?: string | null;
};

type SocialAccountRecord = {
  id: string;
  business_profile_id: string;
  platform: PlatformKey;
  account_name: string;
  status: string;
};

type PickedMedia = {
  uri: string;
  name: string;
  mimeType: string;
  type: 'image' | 'video';
  size?: number;
};

type ProfileResult = {
  id: string;
  user_id: string;
  business_name: string;
  niche: string;
};

type PlatformSuggestion = {
  platform: string;
  suggestions: Array<{
    title: string;
    format: string;
    hook: string;
    caption: string;
    cta: string;
    on_screen_text: string[];
    aspect_ratio: string;
    duration_seconds: string;
    platform_format: string;
    sound_direction: string;
    asset_ids: string[];
  }>;
};

type RankedAsset = {
  asset_id: string;
  title: string;
  asset_type: string;
  score: number;
  reason: string;
};

type TrendInsight = {
  format: string;
  label: string;
  source: string;
  live_trend_data_available: boolean;
};

const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || '').trim().replace(/\/+$/, '');
const apiUrl = (path: string) => {
  if (!API_BASE_URL) {
    throw new Error('Backend URL is missing from this app build. Check EXPO_PUBLIC_API_BASE_URL in frontend/.env and rebuild the app.');
  }
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
};
const mediaAssetUploadUrl = (profileId: string) =>
  apiUrl(`/api/v1/business-profiles/${encodeURIComponent(profileId)}/media-assets`);
const BUSINESS_PROFILE_CACHE_KEY = 'localbiz.business-profile.v1';
const LOCAL_USER_ID_KEY = 'localbiz.user-id.v1';

const createLocalUserId = () =>
  `user-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;

const PLATFORM_OPTIONS: Array<{ key: PlatformKey; label: string }> = [
  { key: 'instagram', label: 'Instagram' },
  { key: 'tiktok', label: 'TikTok' },
  { key: 'snapchat', label: 'Snapchat' },
  { key: 'youtube', label: 'YouTube' },
];

const TREND_FORMAT_OPTIONS = [
  { key: 'auto', label: 'Auto' },
  { key: 'before_after', label: 'Before / after' },
  { key: 'educational_tip', label: 'Quick tip' },
  { key: 'behind_scenes', label: 'Behind the scenes' },
  { key: 'customer_story', label: 'Customer story' },
  { key: 'offer_spotlight', label: 'Offer spotlight' },
];

const CONTENT_TYPE_OPTIONS: Array<{ key: GeneratedContentType; label: string; description: string }> = [
  { key: 'text', label: 'Text post', description: 'Ready-to-publish post copy' },
  { key: 'image', label: 'Image brief', description: 'Text brief for a future image generator' },
  { key: 'video', label: 'Video brief', description: 'Text brief for a future video generator' },
];

const defaultProfile: BusinessProfileForm = {
  business_name: '',
  niche: '',
  location: '',
  service_offerings: '',
  target_audience: '',
  brand_tone: '',
  posting_goals: '',
};

const defaultAsset: ContentAssetForm = {
  asset_type: 'text',
  title: '',
  source_text: '',
  description: '',
};

export default function App() {
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<BusinessProfileForm>(defaultProfile);
  const [selectedPlatforms, setSelectedPlatforms] = useState<PlatformKey[]>(['instagram', 'tiktok']);
  const [asset, setAsset] = useState<ContentAssetForm>(defaultAsset);
  const [assetLibrary, setAssetLibrary] = useState<ContentAssetRecord[]>([]);
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [trendFormat, setTrendFormat] = useState('auto');
  const [profileResult, setProfileResult] = useState<ProfileResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRestoringProfile, setIsRestoringProfile] = useState(true);
  const [suggestions, setSuggestions] = useState<PlatformSuggestion[]>([]);
  const [rankedAssets, setRankedAssets] = useState<RankedAsset[]>([]);
  const [trendInsight, setTrendInsight] = useState<TrendInsight | null>(null);
  const [statusMessage, setStatusMessage] = useState('Create your business profile to get started.');
  const [activePage, setActivePage] = useState<'workflow' | 'uploads' | 'create' | 'compose'>('workflow');
  const [pickedMedia, setPickedMedia] = useState<PickedMedia[]>([]);
  const [isUploadingMedia, setIsUploadingMedia] = useState(false);
  const [generationType, setGenerationType] = useState<GeneratedContentType>('text');
  const [generatedContent, setGeneratedContent] = useState<GeneratedContentRecord[]>([]);
  const [generationJobs, setGenerationJobs] = useState<ContentGenerationJobRecord[]>([]);
  const [isGeneratingContent, setIsGeneratingContent] = useState(false);
  const [socialAccounts, setSocialAccounts] = useState<SocialAccountRecord[]>([]);
  const [selectedSocialAccountId, setSelectedSocialAccountId] = useState<string | null>(null);
  const [selectedGeneratedContent, setSelectedGeneratedContent] = useState<GeneratedContentRecord | null>(null);
  const [isLoadingSocialAccounts, setIsLoadingSocialAccounts] = useState(false);

  const canContinue = useMemo(() => {
    const required = [
      profile.business_name,
      profile.niche,
      profile.location,
      profile.service_offerings,
      profile.target_audience,
      profile.brand_tone,
      profile.posting_goals,
    ];
    return required.every(Boolean);
  }, [profile]);

  useEffect(() => {
    let isMounted = true;

    const restoreBusinessProfile = async () => {
      try {
        const cachedValue = await AsyncStorage.getItem(BUSINESS_PROFILE_CACHE_KEY);
        if (!cachedValue) {
          return;
        }

        const cached = JSON.parse(cachedValue) as {
          profile?: BusinessProfileForm;
          profile_id?: string;
          user_id?: string;
        };
        const cachedProfile = cached.profile;
        const isComplete = cachedProfile && [
          cachedProfile.business_name,
          cachedProfile.niche,
          cachedProfile.location,
          cachedProfile.service_offerings,
          cachedProfile.target_audience,
          cachedProfile.brand_tone,
          cachedProfile.posting_goals,
        ].every((value) => typeof value === 'string' && value.trim().length > 0);

        if (!isComplete) {
          if (cachedProfile && isMounted) {
            setProfile({ ...defaultProfile, ...cachedProfile });
          }
          return;
        }

        if (isMounted) {
          setProfile(cachedProfile);
          setStatusMessage('Restoring your saved business profile...');
        }

        let userId = cached.user_id ?? await AsyncStorage.getItem(LOCAL_USER_ID_KEY);
        if (!userId) {
          userId = createLocalUserId();
          await AsyncStorage.setItem(LOCAL_USER_ID_KEY, userId);
        }

        let activeProfile: ProfileResult | null = null;
        let syncError: string | null = null;
        try {
          const createResponse = await fetch(apiUrl('/api/v1/business-profile'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...cachedProfile, user_id: userId }),
          });
          if (createResponse.ok) {
            activeProfile = (await createResponse.json()) as ProfileResult;
            await AsyncStorage.setItem(
              BUSINESS_PROFILE_CACHE_KEY,
              JSON.stringify({
                profile: cachedProfile,
                profile_id: activeProfile.id,
                user_id: activeProfile.user_id,
              }),
            );
          } else {
            const errorBody = await createResponse.json().catch(() => null);
            syncError = errorBody?.detail || `Backend returned HTTP ${createResponse.status}.`;
          }
        } catch (error) {
          syncError = error instanceof Error ? error.message : 'Network request failed.';
        }

        if (isMounted) {
          setProfileResult(activeProfile ?? {
            id: `local-${Date.now()}`,
            user_id: userId,
            business_name: cachedProfile.business_name,
            niche: cachedProfile.niche,
          });
          setStatusMessage(
            activeProfile
              ? 'Saved business profile restored.'
              : `Saved business details restored offline. Backend sync failed: ${syncError || 'unknown error'}`,
          );
          setStep(2);
        }
      } catch (error) {
        if (isMounted) {
          setStatusMessage('Create your business profile to get started.');
        }
      } finally {
        if (isMounted) {
          setIsRestoringProfile(false);
        }
      }
    };

    void restoreBusinessProfile();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    const profileId = profileResult?.id;
    if (!profileId || !/^[0-9a-f-]{36}$/i.test(profileId)) return;

    let isMounted = true;
    const restoreContentLibrary = async () => {
      setIsLoadingSocialAccounts(true);
      try {
        const [assetsResult, generatedResult, jobsResult, accountsResult] = await Promise.allSettled([
          fetch(apiUrl(`/api/v1/business-profiles/${profileId}/content-assets`)),
          fetch(apiUrl(`/api/v1/business-profiles/${profileId}/generated-content`)),
          fetch(apiUrl(`/api/v1/business-profiles/${profileId}/generated-content/jobs`)),
          fetch(apiUrl(`/api/v1/business-profiles/${profileId}/social-accounts`)),
        ]);

        if (!isMounted) return;
        if (assetsResult.status === 'fulfilled' && assetsResult.value.ok) {
          const assets = await assetsResult.value.json();
          if (Array.isArray(assets)) setAssetLibrary(assets as ContentAssetRecord[]);
        }
        if (generatedResult.status === 'fulfilled' && generatedResult.value.ok) {
          const items = await generatedResult.value.json();
          if (Array.isArray(items)) setGeneratedContent(items as GeneratedContentRecord[]);
        }
        if (jobsResult.status === 'fulfilled' && jobsResult.value.ok) {
          const jobs = await jobsResult.value.json();
          if (Array.isArray(jobs)) setGenerationJobs(jobs as ContentGenerationJobRecord[]);
        }
        if (accountsResult.status === 'fulfilled' && accountsResult.value.ok) {
          const accounts = await accountsResult.value.json();
          if (Array.isArray(accounts)) {
            const connected = (accounts as SocialAccountRecord[]).filter((account) => account.status === 'connected');
            setSocialAccounts(connected);
            setSelectedSocialAccountId((current) => current ?? connected[0]?.id ?? null);
          }
        }
      } catch {
        // Keep the screen usable with the content already in local state.
      } finally {
        if (isMounted) setIsLoadingSocialAccounts(false);
      }
    };

    void restoreContentLibrary();
    return () => {
      isMounted = false;
    };
  }, [profileResult?.id]);

  useEffect(() => {
    const profileId = profileResult?.id;
    if (activePage !== 'create' || !profileId || !/^[0-9a-f-]{36}$/i.test(profileId)) return;
    let isMounted = true;
    const refreshStatuses = async () => {
      const [assetsResult, generatedResult, jobsResult] = await Promise.allSettled([
        fetch(apiUrl(`/api/v1/business-profiles/${profileId}/content-assets`)),
        fetch(apiUrl(`/api/v1/business-profiles/${profileId}/generated-content`)),
        fetch(apiUrl(`/api/v1/business-profiles/${profileId}/generated-content/jobs`)),
      ]);
      if (!isMounted) return;
      if (assetsResult.status === 'fulfilled' && assetsResult.value.ok) {
        const assets = await assetsResult.value.json();
        if (Array.isArray(assets)) setAssetLibrary(assets as ContentAssetRecord[]);
      }
      if (generatedResult.status === 'fulfilled' && generatedResult.value.ok) {
        const items = await generatedResult.value.json();
        if (Array.isArray(items)) setGeneratedContent(items as GeneratedContentRecord[]);
      }
      if (jobsResult.status === 'fulfilled' && jobsResult.value.ok) {
        const jobs = await jobsResult.value.json();
        if (Array.isArray(jobs)) setGenerationJobs(jobs as ContentGenerationJobRecord[]);
      }
    };
    void refreshStatuses();
    const timer = setInterval(() => void refreshStatuses(), 10000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, [activePage, profileResult?.id]);

  const togglePlatform = (platform: PlatformKey) => {
    setSelectedPlatforms((current) =>
      current.includes(platform)
        ? current.filter((item) => item !== platform)
        : [...current, platform],
    );
  };

  const handleProfileSubmit = async () => {
    if (!canContinue) {
      Alert.alert('Complete profile', 'Please finish all business profile fields before continuing.');
      return;
    }

    setIsSubmitting(true);
    setStatusMessage('Saving your business profile...');

    let userId = await AsyncStorage.getItem(LOCAL_USER_ID_KEY);
    if (!userId) {
      userId = createLocalUserId();
      await AsyncStorage.setItem(LOCAL_USER_ID_KEY, userId);
    }

    try {
      await AsyncStorage.setItem(
        BUSINESS_PROFILE_CACHE_KEY,
        JSON.stringify({ profile, profile_id: null, user_id: userId }),
      );
    } catch (error) {
      setStatusMessage('Could not save the local profile cache. Continuing with server save...');
    }

    try {
      const response = await fetch(apiUrl('/api/v1/business-profile'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...profile, user_id: userId }),
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        throw new Error(errorBody?.detail || `Backend returned HTTP ${response.status}.`);
      }

      const savedProfile = (await response.json()) as ProfileResult;
      await AsyncStorage.setItem(
        BUSINESS_PROFILE_CACHE_KEY,
        JSON.stringify({ profile, profile_id: savedProfile.id, user_id: savedProfile.user_id }),
      );
      setProfileResult(savedProfile);
      setStatusMessage('Profile saved successfully.');
      setStep(2);
    } catch (error) {
      const fallbackProfile: ProfileResult = {
        id: `demo-${Date.now()}`,
        user_id: userId,
        business_name: profile.business_name,
        niche: profile.niche,
      };
      setProfileResult(fallbackProfile);
      const reason = error instanceof Error ? error.message : 'Network request failed.';
      setStatusMessage(`Offline demo mode: backend profile save failed (${reason}).`);
      setStep(2);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePlatformConnect = async (platform: PlatformKey) => {
    if (!profileResult) {
      Alert.alert('No profile found', 'Create your business profile before connecting social accounts.');
      return;
    }

    try {
      await fetch(apiUrl(`/api/v1/business-profiles/${profileResult.id}/social-accounts`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform,
          account_name: `${profileResult.business_name.toLowerCase().replace(/\s+/g, '')}-${platform}`,
          status: 'connected',
          access_token: 'demo-access-token',
        }),
      });
      setStatusMessage(`${platform} account connected successfully.`);
      setStep(3);
    } catch (error) {
      setStatusMessage(`${platform} account connected in demo mode.`);
      setStep(3);
    }
  };

  const handleAssetSubmit = async () => {
    if (!profileResult) {
      Alert.alert('No profile found', 'Create a profile before uploading content.');
      return;
    }

    try {
      const response = await fetch(apiUrl(`/api/v1/business-profiles/${profileResult.id}/content-assets`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...asset,
          title: asset.title || `${profileResult.business_name} content`,
        }),
      });

      if (!response.ok) {
        throw new Error('Content asset could not be uploaded.');
      }

      const savedAsset = (await response.json()) as ContentAssetRecord;
      setAssetLibrary((current) => [savedAsset, ...current]);
      setSelectedAssetIds((current) => [...current, savedAsset.id]);
      setAsset(defaultAsset);
      setStatusMessage(`Added ${savedAsset.title || savedAsset.asset_type} to your content library.`);
    } catch (error) {
      setStatusMessage('Could not save this asset. Check the API connection and try again.');
      Alert.alert('Asset not saved', 'Check that the backend is running and reachable, then try again.');
    }
  };

  const generateSuggestions = async (demoMode = false) => {
    if (!profileResult) {
      return;
    }

    try {
      if (!demoMode) {
        const response = await fetch(apiUrl('/api/v1/content-suggestions/generate'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            business_profile_id: profileResult.id,
            platforms: selectedPlatforms,
            asset_ids: selectedAssetIds,
            trend_format: trendFormat,
          }),
        });

        if (!response.ok) {
          throw new Error('Suggestions were not generated.');
        }

        const payload = await response.json();
        const platformResults = Array.isArray(payload.platforms) ? payload.platforms : [];
        const normalizedResults: PlatformSuggestion[] = platformResults.map((result: any) => ({
          ...result,
          suggestions: Array.isArray(result.suggestions)
            ? result.suggestions.map((suggestion: any) => ({
                ...suggestion,
                format: suggestion.format ?? 'Draft concept',
                aspect_ratio: suggestion.aspect_ratio ?? '9:16',
                duration_seconds: suggestion.duration_seconds ?? '15-30',
                platform_format: suggestion.platform_format ?? 'Short video',
                sound_direction:
                  suggestion.sound_direction ?? 'Choose audio that is approved for use on the platform.',
                on_screen_text: Array.isArray(suggestion.on_screen_text)
                  ? suggestion.on_screen_text
                  : [],
                asset_ids: Array.isArray(suggestion.asset_ids) ? suggestion.asset_ids : [],
              }))
            : [],
        }));
        setSuggestions(normalizedResults);
        setRankedAssets(Array.isArray(payload.selected_assets) ? payload.selected_assets : []);
        setTrendInsight(payload.trend_insight ?? null);
        setStatusMessage('Content drafts are ready for the selected platforms.');
        return;
      }
    } catch (error) {
      // fallback demo suggestions
    }

    const demoSuggestions: PlatformSuggestion[] = selectedPlatforms.map((platform) => ({
      platform,
      suggestions: [
        {
          title: `${profileResult.business_name} ${platform} hook`,
          format: 'Quick educational tip',
          hook: `See how ${profileResult.business_name} helps ${profile.target_audience || 'local customers'} get better results.`,
          caption: `${profile.service_offerings}. Book today and experience the difference.`,
          cta: 'Book your consultation today',
          on_screen_text: ['A quick tip from your local team', 'One useful step to try', 'Book with our local team'],
          aspect_ratio: '9:16',
          duration_seconds: '15-30',
          platform_format: platform === 'youtube' ? 'Short' : 'Short video',
          sound_direction: 'Use an original voiceover or a sound licensed within the platform.',
          asset_ids: selectedAssetIds,
        },
        {
          title: `${platform} transformation story`,
          format: 'Before and after',
          hook: 'Before and after results your customers will notice instantly.',
          caption: `Trusted by ${profile.niche.toLowerCase()} clients who care about quality and convenience.`,
          cta: 'DM us to get started',
          on_screen_text: ['The result', 'A detail that made a difference', 'Send us a message'],
          aspect_ratio: '9:16',
          duration_seconds: '15-30',
          platform_format: platform === 'youtube' ? 'Short' : 'Short video',
          sound_direction: 'Use an original voiceover or a sound licensed within the platform.',
          asset_ids: selectedAssetIds,
        },
        {
          title: `${platform} trust builder`,
          format: 'Behind the scenes',
          hook: 'Simple, reliable local service that keeps results consistent.',
          caption: `A friendly, professional experience designed for ${profile.location}.`,
          cta: 'Learn more today',
          on_screen_text: ['Come behind the scenes', 'Care is in the details', 'Learn more today'],
          aspect_ratio: '9:16',
          duration_seconds: '15-30',
          platform_format: platform === 'youtube' ? 'Short' : 'Short video',
          sound_direction: 'Use an original voiceover or a sound licensed within the platform.',
          asset_ids: selectedAssetIds,
        },
      ],
    }));

    setSuggestions(demoSuggestions);
    setRankedAssets([]);
    setTrendInsight({
      format: 'educational_tip',
      label: 'Quick educational tip',
      source: 'local demo templates',
      live_trend_data_available: false,
    });
    setStatusMessage('Demo drafts ready. Connect the backend for asset ranking.');
  };

  const toggleAssetSelection = (assetId: string) => {
    setSelectedAssetIds((current) =>
      current.includes(assetId)
        ? current.filter((id) => id !== assetId)
        : [...current, assetId],
    );
  };

  const pickMedia = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Photo access needed', 'Allow photo library access to choose images or videos.');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images', 'videos'],
      allowsMultipleSelection: true,
      selectionLimit: 10,
      quality: 0.85,
    });
    if (result.canceled) return;

    const media = result.assets.map((item) => ({
      uri: item.uri,
      name: item.fileName || `localbiz-${Date.now()}.${item.type === 'video' ? 'mp4' : 'jpg'}`,
      mimeType: item.mimeType || (item.type === 'video' ? 'video/mp4' : 'image/jpeg'),
      type: item.type === 'video' ? 'video' as const : 'image' as const,
      size: item.fileSize,
    }));
    setPickedMedia((current) => [...current, ...media]);
  };

  const uploadPickedMedia = async () => {
    if (!profileResult || pickedMedia.length === 0) {
      Alert.alert('Choose media first', 'Select at least one image or video to upload.');
      return;
    }

    setIsUploadingMedia(true);
    try {
      for (const media of pickedMedia) {
        const uploadUrl = mediaAssetUploadUrl(profileResult.id);
        let response: Awaited<ReturnType<typeof FileSystem.uploadAsync>>;
        try {
          response = await FileSystem.uploadAsync(
            uploadUrl,
            media.uri,
            {
              fieldName: 'file',
              httpMethod: 'POST',
              mimeType: media.mimeType,
              uploadType: FileSystem.FileSystemUploadType.MULTIPART,
            },
          );
        } catch (error) {
          const reason = error instanceof Error ? error.message : 'Network request failed';
          throw new Error(`Could not reach ${uploadUrl}: ${reason}`);
        }
        let responseBody: any = null;
        try {
          responseBody = JSON.parse(response.body);
        } catch {
          // Keep the status-based fallback below for non-JSON error responses.
        }
        if (response.status < 200 || response.status >= 300) {
          const errorBody = responseBody;
          const detail = errorBody?.detail || response.body?.trim().slice(0, 300);
          throw new Error(
            detail
              ? `Upload endpoint returned HTTP ${response.status}: ${detail}`
              : `Upload endpoint returned HTTP ${response.status} for ${media.name}`,
          );
        }
        const savedAsset = responseBody as ContentAssetRecord;
        if (!savedAsset?.id) {
          throw new Error(`Upload response was invalid for ${media.name}`);
        }
        setAssetLibrary((current) => [savedAsset, ...current]);
        setSelectedAssetIds((current) => [...current, savedAsset.id]);
      }
      setPickedMedia([]);
      setStatusMessage('Selected images and videos were uploaded for content analysis.');
      Alert.alert('Upload complete', 'Your media is ready to be used when creating video drafts.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not upload the selected media.';
      setStatusMessage(message);
      Alert.alert('Upload failed', message);
    } finally {
      setIsUploadingMedia(false);
    }
  };

  const generateNewContent = async () => {
    if (!profileResult || !/^[0-9a-f-]{36}$/i.test(profileResult.id)) {
      Alert.alert('Business profile needed', 'Save or reconnect your business profile before generating content.');
      return;
    }

    setIsGeneratingContent(true);
    setStatusMessage('Using your latest analyzed uploads to create three ideas...');
    try {
      const response = await fetch(
        apiUrl(`/api/v1/business-profiles/${profileResult.id}/generated-content/generate`),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content_type: generationType }),
        },
      );
      const queued = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(queued?.detail || `Content generation failed (HTTP ${response.status}).`);
      }

      if (!queued?.job_id) {
        throw new Error('The server did not return a content generation job ID.');
      }
      setGenerationJobs((current) => [
        { job_id: queued.job_id, status: queued.status || 'pending', content_type: generationType, items: [] },
        ...current.filter((job) => job.job_id !== queued.job_id),
      ]);

      let finishedItems: GeneratedContentRecord[] | null = null;
      for (let attempt = 0; attempt < 1200; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        const pollResponse = await fetch(
          apiUrl(`/api/v1/business-profiles/${profileResult.id}/generated-content/jobs/${queued.job_id}`),
        );
        const job = await pollResponse.json().catch(() => null);
        if (!pollResponse.ok) {
          throw new Error(job?.detail || `Could not check generation status (HTTP ${pollResponse.status}).`);
        }
        if (job?.status) {
          setGenerationJobs((current) => [
            { ...job, content_type: generationType },
            ...current.filter((entry) => entry.job_id !== queued.job_id),
          ]);
        }
        if (job?.status === 'failed') {
          throw new Error(job.error_message || 'The content generation worker could not complete this request.');
        }
        if (job?.status === 'complete') {
          finishedItems = Array.isArray(job.items) ? job.items as GeneratedContentRecord[] : [];
          break;
        }
        setStatusMessage(
          job?.status === 'processing'
            ? 'Gemma is creating your three ideas. This may take a few minutes...'
            : 'Your content request is queued for Gemma...',
        );
      }
      const completedItems = finishedItems;
      if (!completedItems || completedItems.length !== 3) {
        throw new Error('Generation is still running. Your request remains queued; check the content library again shortly.');
      }
      setGeneratedContent((current) => [...completedItems, ...current]);
      setGenerationJobs((current) => current.map((job) =>
        job.job_id === queued.job_id ? { ...job, status: 'complete', items: completedItems } : job,
      ));
      setStatusMessage(`Three ${generationType} content ideas were saved to your content library.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not generate content.';
      setStatusMessage(message);
      Alert.alert('Content generation failed', message);
    } finally {
      setIsGeneratingContent(false);
    }
  };

  const openContentComposer = async (item: GeneratedContentRecord) => {
    setSelectedGeneratedContent(item);
    setSelectedSocialAccountId((current) =>
      socialAccounts.some((account) => account.id === current)
        ? current
        : socialAccounts[0]?.id ?? null,
    );
    setActivePage('compose');
    const profileId = profileResult?.id;
    if (!profileId || !/^[0-9a-f-]{36}$/i.test(profileId)) return;

    setIsLoadingSocialAccounts(true);
    try {
      const response = await fetch(apiUrl(`/api/v1/business-profiles/${profileId}/social-accounts`));
      if (!response.ok) return;
      const accounts = await response.json();
      if (!Array.isArray(accounts)) return;
      const connected = (accounts as SocialAccountRecord[]).filter((account) => account.status === 'connected');
      setSocialAccounts(connected);
      setSelectedSocialAccountId((current) =>
        connected.some((account) => account.id === current) ? current : connected[0]?.id ?? null,
      );
    } catch {
      // Keep the previously loaded connected account list visible if refresh fails.
    } finally {
      setIsLoadingSocialAccounts(false);
    }
  };

  const shareSelectedContent = async () => {
    if (!selectedGeneratedContent) return;
    const selectedAccount = socialAccounts.find((account) => account.id === selectedSocialAccountId);
    if (!selectedAccount) {
      Alert.alert('Choose an account', 'Select one of your connected social accounts first.');
      return;
    }

    try {
      await Share.share(
        {
          title: selectedGeneratedContent.title,
          message: `${selectedGeneratedContent.title}\n\n${selectedGeneratedContent.body}`,
        },
        { dialogTitle: `Share to ${selectedAccount.platform}` },
      );
      setStatusMessage(
        `Share options opened for ${selectedAccount.platform}. Finish and confirm the post in that social app.`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not open the share options.';
      Alert.alert('Could not share post text', message);
    }
  };

  const renderProfileStep = () => (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Phase 1: Business profile</Text>
      <TextInput
        style={styles.input}
        placeholder="Business name"
        placeholderTextColor="#68786e"
        value={profile.business_name}
        onChangeText={(value) => setProfile({ ...profile, business_name: value })}
      />
      <TextInput
        style={styles.input}
        placeholder="Business niche"
        placeholderTextColor="#68786e"
        value={profile.niche}
        onChangeText={(value) => setProfile({ ...profile, niche: value })}
      />
      <TextInput
        style={styles.input}
        placeholder="Location"
        placeholderTextColor="#68786e"
        value={profile.location}
        onChangeText={(value) => setProfile({ ...profile, location: value })}
      />
      <TextInput
        style={styles.input}
        placeholder="Services offered"
        placeholderTextColor="#68786e"
        value={profile.service_offerings}
        onChangeText={(value) => setProfile({ ...profile, service_offerings: value })}
      />
      <TextInput
        style={styles.input}
        placeholder="Target audience"
        placeholderTextColor="#68786e"
        value={profile.target_audience}
        onChangeText={(value) => setProfile({ ...profile, target_audience: value })}
      />
      <TextInput
        style={styles.input}
        placeholder="Brand tone"
        placeholderTextColor="#68786e"
        value={profile.brand_tone}
        onChangeText={(value) => setProfile({ ...profile, brand_tone: value })}
      />
      <TextInput
        style={styles.input}
        placeholder="Posting goals"
        placeholderTextColor="#68786e"
        value={profile.posting_goals}
        onChangeText={(value) => setProfile({ ...profile, posting_goals: value })}
      />

      <TouchableOpacity
        style={[styles.primaryButton, !canContinue && styles.disabledButton]}
        onPress={handleProfileSubmit}
        disabled={isSubmitting || !canContinue}
      >
        <Text style={styles.primaryButtonText}>{isSubmitting ? 'Saving...' : 'Save business profile'}</Text>
      </TouchableOpacity>
    </View>
  );

  const renderAccountStep = () => (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Phase 2: Platform connections</Text>
      <Text style={styles.helperText}>Choose the platforms to connect and manage growth for.</Text>
      {profileResult && (
        <View style={styles.savedProfileSummary}>
          <Text style={styles.savedProfileName}>{profileResult.business_name}</Text>
          <Text style={styles.savedProfileDetails}>{profileResult.niche}</Text>
          <TouchableOpacity onPress={() => setStep(1)}>
            <Text style={styles.editProfileText}>Edit business details</Text>
          </TouchableOpacity>
        </View>
      )}
      {PLATFORM_OPTIONS.map(({ key, label }) => (
        <TouchableOpacity
          key={key}
          style={[
            styles.platformRow,
            selectedPlatforms.includes(key) && styles.platformSelected,
          ]}
          onPress={() => {
            togglePlatform(key);
            handlePlatformConnect(key);
          }}
        >
          <Text style={styles.platformText}>{label}</Text>
          <Text style={styles.platformBadge}>{selectedPlatforms.includes(key) ? 'Connected' : 'Connect'}</Text>
        </TouchableOpacity>
      ))}

      <TouchableOpacity style={styles.secondaryButton} onPress={() => setStep(3)}>
        <Text style={styles.secondaryButtonText}>Continue to content intake</Text>
      </TouchableOpacity>
    </View>
  );

  const renderAssetStep = () => (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Content studio</Text>
      <Text style={styles.helperText}>Add source material, select the strongest inputs, then generate three drafts for each platform.</Text>

      <Text style={styles.label}>Asset type</Text>
      <View style={styles.chipRow}>
        {(['image', 'video', 'text'] as const).map((type) => (
          <TouchableOpacity
            key={type}
            style={[styles.chip, asset.asset_type === type && styles.chipSelected]}
            onPress={() => setAsset({ ...asset, asset_type: type })}
          >
            <Text style={[styles.chipText, asset.asset_type === type && styles.chipTextSelected]}>{type}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TextInput
        style={styles.input}
        placeholder="Content title"
        placeholderTextColor="#68786e"
        value={asset.title}
        onChangeText={(value) => setAsset({ ...asset, title: value })}
      />
      <TextInput
        style={[styles.input, styles.textArea]}
        placeholder="Paste text or describe the content idea"
        placeholderTextColor="#68786e"
        multiline
        numberOfLines={5}
        value={asset.source_text}
        onChangeText={(value) => setAsset({ ...asset, source_text: value })}
      />
      <TextInput
        style={[styles.input, styles.textArea]}
        placeholder="Optional description or notes"
        placeholderTextColor="#68786e"
        multiline
        numberOfLines={4}
        value={asset.description}
        onChangeText={(value) => setAsset({ ...asset, description: value })}
      />

      <TouchableOpacity style={styles.primaryButton} onPress={handleAssetSubmit}>
        <Text style={styles.primaryButtonText}>Add to content library</Text>
      </TouchableOpacity>

      <View style={styles.librarySection}>
        <Text style={styles.sectionTitle}>Your content library</Text>
        {assetLibrary.length === 0 ? (
          <Text style={styles.emptyState}>Your saved source material will appear here.</Text>
        ) : (
          assetLibrary.map((libraryAsset) => {
            const isSelected = selectedAssetIds.includes(libraryAsset.id);
            return (
              <TouchableOpacity
                key={libraryAsset.id}
                style={[styles.assetRow, isSelected && styles.assetRowSelected]}
                onPress={() => toggleAssetSelection(libraryAsset.id)}
              >
                <View style={styles.assetCopy}>
                  <Text style={styles.assetTitle}>{libraryAsset.title || 'Untitled source'}</Text>
                  <Text style={styles.assetMeta}>{libraryAsset.asset_type.toUpperCase()} · {isSelected ? 'Selected' : 'Tap to select'}</Text>
                </View>
                <Text style={styles.assetCheck}>{isSelected ? '✓' : '+'}</Text>
              </TouchableOpacity>
            );
          })
        )}
      </View>

      <View style={styles.librarySection}>
        <Text style={styles.sectionTitle}>Creative direction</Text>
        <Text style={styles.helperText}>Choose an angle or let the asset type guide a starting format. This is not live trend data.</Text>
        <View style={styles.chipRow}>
          {TREND_FORMAT_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option.key}
              style={[styles.chip, trendFormat === option.key && styles.chipSelected]}
              onPress={() => setTrendFormat(option.key)}
            >
              <Text style={[styles.chipText, trendFormat === option.key && styles.chipTextSelected]}>{option.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity style={styles.primaryButton} onPress={() => generateSuggestions()}>
          <Text style={styles.primaryButtonText}>Rank sources and generate drafts</Text>
        </TouchableOpacity>
      </View>

      {suggestions.length > 0 && (
        <View style={styles.resultContainer}>
          <Text style={styles.sectionTitle}>Phase 4: Best source material</Text>
          {trendInsight && (
            <View style={styles.insightBanner}>
              <Text style={styles.insightTitle}>Creative direction: {trendInsight.label}</Text>
              <Text style={styles.insightText}>Based on {trendInsight.source}. Live trend signals are not connected yet.</Text>
            </View>
          )}
          {rankedAssets.length > 0 ? rankedAssets.map((rankedAsset, index) => (
            <View key={rankedAsset.asset_id} style={styles.rankedAssetRow}>
              <View style={styles.rankBadge}><Text style={styles.rankBadgeText}>{index + 1}</Text></View>
              <View style={styles.assetCopy}>
                <Text style={styles.assetTitle}>{rankedAsset.title}</Text>
                <Text style={styles.assetMeta}>{rankedAsset.asset_type} · Relevance {rankedAsset.score}/100</Text>
                <Text style={styles.insightText}>{rankedAsset.reason}</Text>
              </View>
            </View>
          )) : (
            <Text style={styles.emptyState}>No saved assets selected. Drafts will use your business profile only.</Text>
          )}

          <Text style={[styles.sectionTitle, styles.phaseFiveTitle]}>Phase 5: Draft variations</Text>
          {suggestions.map((platformSuggestion) => (
            <View key={platformSuggestion.platform} style={styles.platformSuggestionCard}>
              <Text style={styles.platformSuggestionTitle}>{platformSuggestion.platform.toUpperCase()}</Text>
              {platformSuggestion.suggestions.map((suggestion, index) => (
                <View key={`${platformSuggestion.platform}-${index}`} style={styles.suggestionCard}>
                  <Text style={styles.suggestionTitle}>{suggestion.title}</Text>
                  <Text style={styles.suggestionMeta}>{suggestion.platform_format} · {suggestion.aspect_ratio} · {suggestion.duration_seconds}s</Text>
                  <Text style={styles.suggestionText}>Angle: {suggestion.format}</Text>
                  <Text style={styles.suggestionText}>Hook: {suggestion.hook}</Text>
                  <Text style={styles.suggestionText}>Caption: {suggestion.caption}</Text>
                  <Text style={styles.suggestionText}>CTA: {suggestion.cta}</Text>
                  <Text style={styles.suggestionText}>On-screen: {suggestion.on_screen_text.join(' / ')}</Text>
                  <Text style={styles.suggestionText}>Sound: {suggestion.sound_direction}</Text>
                </View>
              ))}
            </View>
          ))}
        </View>
      )}
    </View>
  );

  const renderMediaUploadPage = () => (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Your video ingredients</Text>
      <Text style={styles.helperText}>Choose images and clips you own or have permission to use. They’ll be attached to your business profile for future content analysis.</Text>
      <TouchableOpacity style={styles.primaryButton} onPress={pickMedia}>
        <Text style={styles.primaryButtonText}>Choose images or videos</Text>
      </TouchableOpacity>
      {pickedMedia.length === 0 ? (
        <Text style={styles.emptyState}>No media selected yet.</Text>
      ) : (
        <View style={styles.mediaGrid}>
          {pickedMedia.map((media, index) => (
            <View key={`${media.uri}-${index}`} style={styles.mediaItem}>
              {media.type === 'image' ? (
                <Image source={{ uri: media.uri }} style={styles.mediaPreview} />
              ) : (
                <View style={styles.videoPreview}><Text style={styles.videoPreviewText}>VIDEO</Text></View>
              )}
              <Text numberOfLines={1} style={styles.mediaName}>{media.name}</Text>
              <TouchableOpacity onPress={() => setPickedMedia((current) => current.filter((_, itemIndex) => itemIndex !== index))}>
                <Text style={styles.removeMedia}>Remove</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}
      <TouchableOpacity
        style={[styles.primaryButton, (pickedMedia.length === 0 || isUploadingMedia) && styles.disabledButton]}
        disabled={pickedMedia.length === 0 || isUploadingMedia}
        onPress={uploadPickedMedia}
      >
        <Text style={styles.primaryButtonText}>{isUploadingMedia ? 'Uploading...' : 'Upload selected media'}</Text>
      </TouchableOpacity>
      <Text style={styles.helperText}>Images and videos are saved to the backend’s configured media directory. Model-based analysis will be a later processing step.</Text>
    </View>
  );

  const renderCreateContentPage = () => (
    <View>
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Create content</Text>
        <Text style={styles.helperText}>
          Choose a content type. Gemma uses your business profile and up to the five latest completed upload analyses.
          Image and video selections return text briefs for now; media rendering will be added later.
        </Text>
        {CONTENT_TYPE_OPTIONS.map((option) => (
          <TouchableOpacity
            key={option.key}
            style={[styles.platformRow, generationType === option.key && styles.platformSelected]}
            accessibilityRole="radio"
            accessibilityState={{ selected: generationType === option.key }}
            onPress={() => setGenerationType(option.key)}
          >
            <View style={styles.assetCopy}>
              <Text style={styles.platformText}>{option.label}</Text>
              <Text style={styles.assetMeta}>{option.description}</Text>
            </View>
            <Text style={styles.assetCheck}>{generationType === option.key ? '✓' : '○'}</Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity
          style={[styles.primaryButton, (isGeneratingContent || !profileResult) && styles.disabledButton]}
          disabled={isGeneratingContent || !profileResult}
          onPress={generateNewContent}
        >
          <Text style={styles.primaryButtonText}>
            {isGeneratingContent ? 'Generating...' : 'Generate three ideas'}
          </Text>
        </TouchableOpacity>
        <Text style={styles.helperText}>
          Generation requires at least one completed upload analysis. New ideas are saved automatically.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Your saved source library</Text>
        {assetLibrary.length === 0 ? (
          <Text style={styles.emptyState}>No uploaded or saved source content found for this profile yet.</Text>
        ) : assetLibrary.map((libraryAsset) => (
          <View key={libraryAsset.id} style={styles.rankedAssetRow}>
            <View style={styles.assetCopy}>
              <Text style={styles.assetTitle}>{libraryAsset.title || 'Untitled source'}</Text>
              <Text style={styles.assetMeta}>{libraryAsset.asset_type.toUpperCase()}</Text>
              <Text style={styles.suggestionMeta}>{libraryAsset.content_generation_status || 'pending content generation'}</Text>
              {!!libraryAsset.description && <Text style={styles.insightText}>{libraryAsset.description}</Text>}
            </View>
          </View>
        ))}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Content generation status</Text>
        {generationJobs.length === 0 ? (
          <Text style={styles.emptyState}>No content generation requests yet.</Text>
        ) : generationJobs.map((job) => {
          const statusLabel = job.status === 'complete'
            ? 'Completed content generation'
            : job.status === 'processing'
              ? 'Processing content generation'
              : job.status === 'failed'
                ? 'Content generation failed'
                : 'Pending content generation';
          return (
            <View key={job.job_id} style={styles.rankedAssetRow}>
              <View style={styles.assetCopy}>
                <Text style={styles.assetTitle}>{job.content_type.toUpperCase()} content request</Text>
                <Text style={styles.suggestionMeta}>{statusLabel}</Text>
                {!!job.error_message && <Text style={styles.insightText}>{job.error_message}</Text>}
              </View>
            </View>
          );
        })}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Generated content library</Text>
        {generatedContent.length === 0 ? (
          <Text style={styles.emptyState}>Generated text and media briefs will appear here.</Text>
        ) : generatedContent.map((item) => (
          <TouchableOpacity
            key={item.id}
            style={styles.suggestionCard}
            accessibilityRole="button"
            accessibilityLabel={`Review and share ${item.title}`}
            onPress={() => openContentComposer(item)}
          >
            <Text style={styles.suggestionTitle}>{item.title}</Text>
            <Text style={styles.suggestionMeta}>{item.content_type.toUpperCase()} · {new Date(item.created_at).toLocaleDateString()}</Text>
            <Text style={styles.suggestionMeta}>Completed content generation</Text>
            <Text style={styles.suggestionText}>{item.body}</Text>
            <Text style={styles.editProfileText}>Tap to review and share</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  const renderContentComposer = () => (
    <View style={styles.card}>
      <TouchableOpacity onPress={() => setActivePage('create')}>
        <Text style={styles.editProfileText}>‹ Back to content library</Text>
      </TouchableOpacity>
      <Text style={styles.sectionTitle}>Review post</Text>
      {!selectedGeneratedContent ? (
        <Text style={styles.emptyState}>Choose an item from your generated content library.</Text>
      ) : (
        <>
          <Text style={styles.suggestionMeta}>{selectedGeneratedContent.content_type.toUpperCase()} CONTENT</Text>
          <Text style={styles.suggestionTitle}>{selectedGeneratedContent.title}</Text>
          <View style={styles.suggestionCard}>
            <Text style={styles.suggestionText}>{selectedGeneratedContent.body}</Text>
          </View>

          <Text style={styles.sectionTitle}>Choose a connected account</Text>
          {isLoadingSocialAccounts ? (
            <Text style={styles.emptyState}>Loading your connected accounts...</Text>
          ) : socialAccounts.length === 0 ? (
            <View>
              <Text style={styles.emptyState}>No connected social accounts were found for this business profile.</Text>
              <TouchableOpacity style={styles.secondaryButton} onPress={() => setActivePage('workflow')}>
                <Text style={styles.secondaryButtonText}>Go to platform connections</Text>
              </TouchableOpacity>
            </View>
          ) : socialAccounts.map((account) => (
            <TouchableOpacity
              key={account.id}
              style={[styles.platformRow, selectedSocialAccountId === account.id && styles.platformSelected]}
              accessibilityRole="radio"
              accessibilityState={{ selected: selectedSocialAccountId === account.id }}
              onPress={() => setSelectedSocialAccountId(account.id)}
            >
              <View style={styles.assetCopy}>
                <Text style={styles.platformText}>{account.platform}</Text>
                <Text style={styles.assetMeta}>{account.account_name}</Text>
              </View>
              <Text style={styles.assetCheck}>{selectedSocialAccountId === account.id ? '✓' : '○'}</Text>
            </TouchableOpacity>
          ))}

          <Text style={styles.helperText}>
            Share options open on your phone. Select the social app and finish the post there; this app does not publish directly to social platforms yet.
          </Text>
          <TouchableOpacity
            style={[styles.primaryButton, (!selectedSocialAccountId || socialAccounts.length === 0) && styles.disabledButton]}
            disabled={!selectedSocialAccountId || socialAccounts.length === 0}
            onPress={shareSelectedContent}
          >
            <Text style={styles.primaryButtonText}>Open share options</Text>
          </TouchableOpacity>
        </>
      )}
    </View>
  );

  return (
    <View style={styles.screen}>
      <StatusBar style="dark" />
      <View style={styles.topBar}>
        <Text style={styles.appTitle}>LocalBiz Growth</Text>
        <Text style={styles.statusText}>{statusMessage}</Text>
      </View>

      <View style={styles.bottomNav} accessibilityRole="tablist">
        <TouchableOpacity
          style={[styles.navButton, activePage === 'workflow' && styles.navButtonActive]}
          accessibilityRole="tab"
          accessibilityState={{ selected: activePage === 'workflow' }}
          onPress={() => setActivePage('workflow')}
        >
          <Text style={[styles.navText, activePage === 'workflow' && styles.navTextActive]}>Workflow</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.navButton, activePage === 'uploads' && styles.navButtonActive]}
          accessibilityRole="tab"
          accessibilityState={{ selected: activePage === 'uploads' }}
          onPress={() => setActivePage('uploads')}
        >
          <Text style={[styles.navText, activePage === 'uploads' && styles.navTextActive]}>Upload media</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.navButton, (activePage === 'create' || activePage === 'compose') && styles.navButtonActive]}
          accessibilityRole="tab"
          accessibilityState={{ selected: activePage === 'create' }}
          onPress={() => setActivePage('create')}
        >
          <Text style={[styles.navText, (activePage === 'create' || activePage === 'compose') && styles.navTextActive]}>Create content</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {activePage === 'uploads'
          ? renderMediaUploadPage()
          : activePage === 'compose'
            ? renderContentComposer()
            : activePage === 'create'
              ? renderCreateContentPage()
              : (
          <>
            {isRestoringProfile ? (
              <View style={styles.card}>
                <Text style={styles.sectionTitle}>Checking saved business details...</Text>
              </View>
            ) : step === 1 && renderProfileStep()}
            {step === 2 && renderAccountStep()}
            {step === 3 && renderAssetStep()}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#f2f6f3',
  },
  topBar: {
    paddingTop: 60,
    paddingHorizontal: 20,
    paddingBottom: 16,
    backgroundColor: '#e4efe8',
    borderBottomWidth: 1,
    borderColor: '#d1dfd6',
  },
  appTitle: {
    color: '#18392b',
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 6,
  },
  statusText: {
    color: '#52675c',
    fontSize: 13,
  },
  content: {
    padding: 20,
    paddingBottom: 40,
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 8,
    padding: 18,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#dce6df',
  },
  sectionTitle: {
    color: '#1d3328',
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 14,
  },
  helperText: {
    color: '#52645a',
    fontSize: 14,
    marginBottom: 16,
  },
  savedProfileSummary: {
    backgroundColor: '#eef4f0',
    borderRadius: 8,
    padding: 12,
    marginBottom: 14,
  },
  savedProfileName: {
    color: '#263a2f',
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 3,
  },
  savedProfileDetails: {
    color: '#627469',
    fontSize: 13,
    marginBottom: 8,
  },
  editProfileText: {
    color: '#247349',
    fontSize: 13,
    fontWeight: '700',
  },
  input: {
    backgroundColor: '#ffffff',
    color: '#17231c',
    borderColor: '#aebfb3',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    marginBottom: 12,
  },
  textArea: {
    minHeight: 110,
    textAlignVertical: 'top',
  },
  primaryButton: {
    backgroundColor: '#27794f',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  disabledButton: {
    opacity: 0.5,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 15,
  },
  secondaryButton: {
    backgroundColor: '#e5a04a',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 12,
  },
  secondaryButtonText: {
    color: '#382510',
    fontWeight: '700',
    fontSize: 15,
  },
  platformRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#cbd9d0',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 14,
    marginBottom: 10,
  },
  platformSelected: {
    borderColor: '#3d9668',
    backgroundColor: '#e5f3e9',
  },
  platformText: {
    color: '#263a2f',
    fontSize: 15,
    fontWeight: '600',
  },
  platformBadge: {
    color: '#247349',
    fontSize: 12,
    fontWeight: '700',
  },
  label: {
    color: '#293c31',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 10,
  },
  chipRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  chip: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#b9c9bf',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  chipSelected: {
    backgroundColor: '#27794f',
    borderColor: '#27794f',
  },
  chipText: {
    color: '#384c40',
    fontSize: 12,
    textTransform: 'capitalize',
  },
  chipTextSelected: {
    color: '#ffffff',
    fontWeight: '700',
  },
  resultContainer: {
    marginTop: 18,
  },
  librarySection: {
    borderTopWidth: 1,
    borderTopColor: '#dce6df',
    marginTop: 20,
    paddingTop: 18,
  },
  emptyState: {
    color: '#5b6e62',
    fontSize: 13,
    lineHeight: 19,
    paddingVertical: 8,
  },
  assetRow: {
    minHeight: 62,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#cbd9d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 8,
  },
  assetRowSelected: {
    borderColor: '#3d9668',
    backgroundColor: '#e5f3e9',
  },
  assetCopy: {
    flex: 1,
  },
  assetTitle: {
    color: '#263a2f',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  assetMeta: {
    color: '#627469',
    fontSize: 11,
    marginBottom: 4,
  },
  assetCheck: {
    color: '#247349',
    fontSize: 20,
    fontWeight: '700',
    paddingLeft: 12,
  },
  insightBanner: {
    backgroundColor: '#fff3df',
    borderLeftWidth: 3,
    borderLeftColor: '#df9634',
    padding: 12,
    marginBottom: 12,
  },
  insightTitle: {
    color: '#573d1e',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 5,
  },
  insightText: {
    color: '#5e6258',
    fontSize: 12,
    lineHeight: 17,
  },
  rankedAssetRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#eef4f0',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  rankBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#d9eddf',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  rankBadgeText: {
    color: '#1e6842',
    fontWeight: '700',
  },
  phaseFiveTitle: {
    marginTop: 20,
  },
  platformSuggestionCard: {
    backgroundColor: '#f0f5f1',
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
    borderWidth: 1,
    borderColor: '#d9e4dc',
  },
  platformSuggestionTitle: {
    color: '#226b47',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 10,
    textTransform: 'uppercase',
  },
  suggestionCard: {
    backgroundColor: '#ffffff',
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#dce6df',
    marginBottom: 10,
  },
  suggestionTitle: {
    color: '#263a2f',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 6,
  },
  suggestionMeta: {
    color: '#247349',
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 7,
  },
  suggestionText: {
    color: '#405348',
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 4,
  },
  mediaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 18 },
  mediaItem: { width: '47%', backgroundColor: '#eef4f0', borderRadius: 8, padding: 8 },
  mediaPreview: { width: '100%', aspectRatio: 1, borderRadius: 6, backgroundColor: '#dce6df' },
  videoPreview: { width: '100%', aspectRatio: 1, borderRadius: 6, backgroundColor: '#294637', alignItems: 'center', justifyContent: 'center' },
  videoPreviewText: { color: '#ffffff', fontSize: 14, fontWeight: '700' },
  mediaName: { color: '#263a2f', fontSize: 12, marginTop: 7 },
  removeMedia: { color: '#9b3e32', fontSize: 12, fontWeight: '700', paddingVertical: 5 },
  bottomNav: { flexDirection: 'row', borderBottomWidth: 1, borderColor: '#d1dfd6', backgroundColor: '#ffffff', paddingHorizontal: 18, paddingVertical: 8 },
  navButton: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingVertical: 7, borderRadius: 8 },
  navButtonActive: { backgroundColor: '#e4efe8' },
  navText: { color: '#52645a', fontSize: 13, fontWeight: '600' },
  navTextActive: { color: '#247349', fontWeight: '800' },
});
