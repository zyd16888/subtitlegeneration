import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Form, Input, Select, Button, message, Spin, Space, InputNumber, Switch, Slider, Collapse,
  Table, Tag, Popconfirm, Typography, Row, Col, Tooltip, Progress, Checkbox, Radio
} from 'antd';
import {
  SaveOutlined, TranslationOutlined, DownloadOutlined,
  CloudServerOutlined, RocketOutlined,
  InfoCircleOutlined, ReloadOutlined, SyncOutlined,
  LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined,
  PlusOutlined, DeleteOutlined, SwapOutlined,
  AimOutlined, ClearOutlined, SendOutlined, ThunderboltOutlined, FilterOutlined,
  GlobalOutlined, SoundOutlined, DatabaseOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { ASRModel, ModelDownloadProgress, LanguageInfo, Library } from '../types/api';

const { Option } = Select;
const { Text } = Typography;

type CategoryKey = 'emby' | 'path' | 'translation' | 'asr' | 'language' | 'audio' | 'models' | 'worker' | 'telegram' | 'cleanup';

interface CategoryDef {
  key: CategoryKey;
  icon: React.ReactNode;
  label: string;
  description: string;
  colorVar: string;
  colorBgVar: string;
}

const CATEGORIES: CategoryDef[] = [
  { key: 'emby',       icon: <CloudServerOutlined />, label: 'Emby 核心节点',    description: '服务器地址 · API 密钥',     colorVar: '--accent-cyan',     colorBgVar: '--accent-cyan-bg' },
  { key: 'path',       icon: <SwapOutlined />,       label: '路径映射',           description: '媒体库路径 · 挂载规则',     colorVar: '--accent-amber',    colorBgVar: '--accent-amber-bg' },
  { key: 'translation',icon: <TranslationOutlined />, label: '翻译服务',         description: 'API 配置 · 引擎切换',      colorVar: '--accent-emerald',  colorBgVar: '--accent-emerald-bg' },
  { key: 'asr',        icon: <AimOutlined />,         label: 'ASR 引擎',           description: '推理引擎 · 云端 API',      colorVar: '--accent-amber',    colorBgVar: '--accent-amber-bg' },
  { key: 'language',   icon: <GlobalOutlined />,      label: '语言与字幕',          description: '源/目标语言 · 检测模式',   colorVar: '--accent-cyan',     colorBgVar: '--accent-cyan-bg' },
  { key: 'audio',      icon: <SoundOutlined />,       label: '音频处理',            description: '降噪 · VAD · 语气词',     colorVar: '--accent-emerald',  colorBgVar: '--accent-emerald-bg' },
  { key: 'models',     icon: <DatabaseOutlined />,    label: '模型管理',            description: '下载激活 · 自适应映射',    colorVar: '--accent-rose',     colorBgVar: '--accent-rose-bg' },
  { key: 'worker',     icon: <ThunderboltOutlined />, label: '任务 Worker',        description: '后台进程 · 并发控制',      colorVar: '--accent-emerald',  colorBgVar: '--accent-emerald-bg' },
  { key: 'telegram',   icon: <SendOutlined />,       label: 'Telegram 机器人',     description: 'Bot Token · 配额控制',     colorVar: '--accent-cyan',     colorBgVar: '--accent-cyan-bg' },
  { key: 'cleanup',    icon: <ClearOutlined />,      label: '临时文件管理',       description: '自动清理 · 磁盘占用',      colorVar: '--accent-rose',     colorBgVar: '--accent-rose-bg' },
];

const DEFAULT_VAD_FORM_VALUES = {
  vad_mode: 'energy' as const,
  vad_threshold: 0.5,
  vad_min_silence_duration: 0.7,
  vad_min_speech_duration: 0.5,
  vad_max_speech_duration: 20,
};

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [savingAll, setSavingAll] = useState(false);
  const [savingEmby, setSavingEmby] = useState(false);
  const [savingTranslation, setSavingTranslation] = useState(false);
  const [savingAsr, setSavingAsr] = useState(false);
  const [savingLanguage, setSavingLanguage] = useState(false);
  const [savingAudio, setSavingAudio] = useState(false);
  const [savingModels, setSavingModels] = useState(false);
  const [savingCleanup, setSavingCleanup] = useState(false);
  const [savingTelegram, setSavingTelegram] = useState(false);
  const [botStatus, setBotStatus] = useState<{ running: boolean; uptime_seconds?: number } | null>(null);
  const [botLoading, setBotLoading] = useState(false);
  const [workerStatus, setWorkerStatus] = useState<{ running: boolean; pid?: number; uptime_seconds?: number } | null>(null);
  const [workerLoading, setWorkerLoading] = useState(false);
  const [testingEmby, setTestingEmby] = useState(false);
  const [testingTranslation, setTestingTranslation] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [cleaningTemp, setCleaningTemp] = useState(false);
  const [diskUsage, setDiskUsage] = useState<{ total_mb: number; task_count: number } | null>(null);
  const [activeCategory, setActiveCategory] = useState<CategoryKey>('emby');
  const [models, setModels] = useState<ASRModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelSearch, setModelSearch] = useState('');
  const [modelLangFilter, setModelLangFilter] = useState<string | undefined>(undefined);
  const [downloadProgress, setDownloadProgress] = useState<Record<string, ModelDownloadProgress>>({});
  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({});
  const [vadModels, setVadModels] = useState<ASRModel[]>([]);
  const [vadModelsLoading, setVadModelsLoading] = useState(false);
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [embyLibraries, setEmbyLibraries] = useState<Library[]>([]);
  const [defaultFillerWords, setDefaultFillerWords] = useState<Record<string, string[]>>({});

  const translationService = Form.useWatch('translation_service', form);
  const enableDenoise = Form.useWatch('enable_denoise', form);
  const enableVad = Form.useWatch('enable_vad', form);
  const vadMode = Form.useWatch('vad_mode', form);
  const googleMode = Form.useWatch('google_translate_mode', form);
  const microsoftMode = Form.useWatch('microsoft_translate_mode', form);
  const deeplMode = Form.useWatch('deepl_mode', form);
  const filterFillerWords = Form.useWatch('filter_filler_words', form);
  const enableLangDetection = Form.useWatch('enable_language_detection', form);
  const enableLidWhitelistFilter = Form.useWatch('lid_filter_whitelist_enabled', form);
  const [langModelMap, setLangModelMap] = useState<Record<string, string>>({});

  const loadConfig = async () => {
    setLoading(true);
    try {
      const config = await api.config.getConfig();
      // 兼容老数据：target_languages 为空时回填为 [target_language]
      if (!config.target_languages || config.target_languages.length === 0) {
        config.target_languages = config.target_language ? [config.target_language] : [];
      }
      form.setFieldsValue(config);
      setLangModelMap(config.asr_language_model_map || {});
      setIsDirty(false);
    } catch (err: any) { message.error(err.message || '加载配置失败'); }
    finally { setLoading(false); }
  };

  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    try { const data = await api.models.listModels(); setModels(data); }
    catch {} finally { setModelsLoading(false); }
  }, []);

  const loadVadModels = useCallback(async () => {
    setVadModelsLoading(true);
    try { const data = await api.models.listVadModels(); setVadModels(data); }
    catch {} finally { setVadModelsLoading(false); }
  }, []);

  const loadLanguages = useCallback(async () => {
    try { const data = await api.models.listLanguages(); setLanguages(data); } catch {}
  }, []);

  const loadEmbyLibraries = useCallback(async () => {
    try { const data = await api.media.getLibraries(); setEmbyLibraries(data); } catch {}
  }, []);

  const loadDiskUsage = useCallback(async () => {
    try { const data = await api.config.getTempDiskUsage(); setDiskUsage({ total_mb: data.total_mb, task_count: data.task_count }); } catch {}
  }, []);

  const loadBotStatus = useCallback(async () => {
    try { const s = await api.config.getBotStatus(); setBotStatus({ running: s.running, uptime_seconds: s.uptime_seconds }); } catch {}
  }, []);

  const loadWorkerStatus = useCallback(async () => {
    try { const s = await api.worker.getStatus(); setWorkerStatus({ running: s.running, pid: s.pid, uptime_seconds: s.uptime_seconds }); } catch {}
  }, []);

  const handleWorkerAction = useCallback(async (action: 'start' | 'stop' | 'restart') => {
    setWorkerLoading(true);
    try {
      const s = await api.worker[action]();
      setWorkerStatus({ running: s.running, pid: s.pid, uptime_seconds: s.uptime_seconds });
      message.success(s.message || '操作成功');
    } catch (err: any) {
      message.error(err.message || '操作失败');
    } finally {
      setWorkerLoading(false);
    }
  }, []);

  useEffect(() => { return () => { Object.values(pollTimers.current).forEach(clearInterval); }; }, []);

  const stopPolling = useCallback((modelId: string) => {
    if (pollTimers.current[modelId]) { clearInterval(pollTimers.current[modelId]); delete pollTimers.current[modelId]; }
  }, []);

  const pollErrorCount = useRef<Record<string, number>>({});
  const pollOnComplete = useRef<Record<string, () => void>>({});

  const startPolling = useCallback((modelId: string, onComplete?: () => void) => {
    stopPolling(modelId);
    pollErrorCount.current[modelId] = 0;
    if (onComplete) pollOnComplete.current[modelId] = onComplete;
    pollTimers.current[modelId] = setInterval(async () => {
      try {
        const progress = await api.models.getDownloadProgress(modelId);
        pollErrorCount.current[modelId] = 0;
        setDownloadProgress(prev => ({ ...prev, [modelId]: progress }));
        if (progress.status === 'completed') {
          stopPolling(modelId); message.success('模型下载完成');
          pollOnComplete.current[modelId]?.();
          delete pollOnComplete.current[modelId];
          setTimeout(() => { setDownloadProgress(prev => { const n = { ...prev }; delete n[modelId]; return n; }); }, 3000);
        } else if (progress.status === 'failed') { stopPolling(modelId); message.error(progress.error || '模型下载失败'); }
      } catch {
        pollErrorCount.current[modelId] = (pollErrorCount.current[modelId] || 0) + 1;
        if (pollErrorCount.current[modelId] >= 10) { stopPolling(modelId); }
      }
    }, 1000);
  }, [stopPolling]);

  const handleDownload = useCallback(async (modelId: string) => {
    try { const progress = await api.models.downloadModel(modelId); setDownloadProgress(prev => ({ ...prev, [modelId]: progress })); startPolling(modelId, loadModels); }
    catch (err: any) { message.error(err.message || '启动下载失败'); }
  }, [startPolling, loadModels]);

  const handleVadDownload = useCallback(async (modelId: string) => {
    try {
      const progress = await api.models.downloadVadModel(modelId);
      setDownloadProgress(prev => ({ ...prev, [modelId]: progress }));
      startPolling(modelId, loadVadModels);
    } catch (err: any) { message.error(err.message || 'VAD 模型下载失败'); }
  }, [startPolling, loadVadModels]);

  const filteredModels = React.useMemo(() => {
    let list = models;
    if (modelSearch) { const kw = modelSearch.toLowerCase(); list = list.filter(m => m.id.toLowerCase().includes(kw) || m.name.toLowerCase().includes(kw)); }
    if (modelLangFilter) { list = list.filter(m => m.languages.includes(modelLangFilter)); }
    return list;
  }, [models, modelSearch, modelLangFilter]);

  const availableLanguages = React.useMemo(() => {
    const s = new Set<string>(); models.forEach(m => m.languages.forEach(l => s.add(l))); return Array.from(s).sort();
  }, [models]);

  useEffect(() => {
    loadConfig(); loadModels(); loadVadModels(); loadLanguages(); loadEmbyLibraries(); loadDiskUsage(); loadBotStatus(); loadWorkerStatus();
    api.config.getDefaultFillerWords().then(setDefaultFillerWords).catch(() => {});
  }, []);

  // Worker 状态轮询（每 5 秒）
  useEffect(() => {
    const t = setInterval(() => { loadWorkerStatus(); }, 5000);
    return () => clearInterval(t);
  }, [loadWorkerStatus]);

  const handleValuesChange = () => { setIsDirty(true); };

  const handleSaveAll = async () => {
    try {
      await form.validateFields();
      setSavingAll(true);
      // form.getFieldsValue(true) 获取所有字段（包括未挂载的），避免分 tab 导致字段丢失
      const values = form.getFieldsValue(true);
      // 过滤掉 undefined/null 字段，避免未加载或禁用字段覆盖数据库中的有效值
      // （例如 asr_model_id 由模型激活流程管理，不应通过全局保存清空）
      const payload = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined && v !== null));
      // 合并 langModelMap（不在 Form 中的独立 state）
      payload.asr_language_model_map = langModelMap;
      await api.config.partialUpdateConfig(payload);
      message.success('核心配置库同步完成');
      setIsDirty(false);
    }
    catch (err: any) { message.error(err.message || '参数校验未通过'); }
    finally { setSavingAll(false); }
  };

  const handleSaveEmby = async () => {
    try { setSavingEmby(true); await api.config.partialUpdateConfig({ emby_url: form.getFieldValue('emby_url'), emby_api_key: form.getFieldValue('emby_api_key') }); message.success('Emby 配置已保存'); }
    catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingEmby(false); }
  };

  const handleSaveTranslation = async () => {
    try {
      const service = form.getFieldValue('translation_service');
      const values: any = { translation_service: service };
      if (service === 'openai') { values.openai_api_key = form.getFieldValue('openai_api_key'); values.openai_model = form.getFieldValue('openai_model'); values.openai_base_url = form.getFieldValue('openai_base_url'); }
      else if (service === 'deepseek') { values.deepseek_api_key = form.getFieldValue('deepseek_api_key'); }
      else if (service === 'local') { values.local_llm_url = form.getFieldValue('local_llm_url'); }
      else if (service === 'google') { values.google_translate_mode = form.getFieldValue('google_translate_mode'); values.google_api_key = form.getFieldValue('google_api_key'); }
      else if (service === 'microsoft') { values.microsoft_translate_mode = form.getFieldValue('microsoft_translate_mode'); values.microsoft_api_key = form.getFieldValue('microsoft_api_key'); values.microsoft_region = form.getFieldValue('microsoft_region'); }
      else if (service === 'baidu') { values.baidu_app_id = form.getFieldValue('baidu_app_id'); values.baidu_secret_key = form.getFieldValue('baidu_secret_key'); }
      else if (service === 'deepl') { values.deepl_mode = form.getFieldValue('deepl_mode'); values.deepl_api_key = form.getFieldValue('deepl_api_key'); values.deeplx_url = form.getFieldValue('deeplx_url'); }
      // 翻译并发数：undefined 表示用户清空 → 提交 null 让后端回退默认
      const concurrency = form.getFieldValue('translation_concurrency');
      values.translation_concurrency = (concurrency === undefined || concurrency === '') ? null : concurrency;
      // 翻译上下文窗口
      const contextSize = form.getFieldValue('translation_context_size');
      values.translation_context_size = (contextSize === undefined || contextSize === '' || contextSize === null) ? 0 : contextSize;
      setSavingTranslation(true); await api.config.partialUpdateConfig(values); message.success('翻译配置已保存');
    } catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingTranslation(false); }
  };

  const handleSaveAsr = async () => {
    try {
      setSavingAsr(true);
      await api.config.partialUpdateConfig({
        asr_engine: form.getFieldValue('asr_engine'),
        asr_model_id: form.getFieldValue('asr_model_id'),
        max_concurrent_tasks: form.getFieldValue('max_concurrent_tasks'),
        cloud_asr_provider: form.getFieldValue('cloud_asr_provider'),
        groq_asr_api_key: form.getFieldValue('groq_asr_api_key'),
        groq_asr_model: form.getFieldValue('groq_asr_model'),
        groq_asr_base_url: form.getFieldValue('groq_asr_base_url'),
        groq_asr_public_audio_base_url: form.getFieldValue('groq_asr_public_audio_base_url'),
        groq_asr_prompt: form.getFieldValue('groq_asr_prompt'),
      });
      message.success('引擎配置已保存');
    } catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingAsr(false); }
  };

  const handleSaveLanguage = async () => {
    try {
      const targetLanguages: string[] = form.getFieldValue('target_languages') || [];
      const primaryTarget = targetLanguages[0] || form.getFieldValue('target_language') || 'zh';
      setSavingLanguage(true);
      await api.config.partialUpdateConfig({
        source_language: form.getFieldValue('source_language'),
        target_language: primaryTarget,
        target_languages: targetLanguages.length > 0 ? targetLanguages : [primaryTarget],
        keep_source_subtitle: !!form.getFieldValue('keep_source_subtitle'),
        source_language_detection: form.getFieldValue('source_language_detection'),
        filter_filler_words: !!form.getFieldValue('filter_filler_words'),
        custom_filler_words: form.getFieldValue('custom_filler_words') || [],
      });
      message.success('语言配置已保存');
    } catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingLanguage(false); }
  };

  const handleSaveAudio = async () => {
    try {
      setSavingAudio(true);
      await api.config.partialUpdateConfig({
        enable_denoise: form.getFieldValue('enable_denoise'),
        enable_vad: form.getFieldValue('enable_vad'),
        vad_mode: form.getFieldValue('vad_mode'),
        vad_model_id: form.getFieldValue('vad_model_id'),
        vad_threshold: form.getFieldValue('vad_threshold'),
        vad_min_silence_duration: form.getFieldValue('vad_min_silence_duration'),
        vad_min_speech_duration: form.getFieldValue('vad_min_speech_duration'),
        vad_max_speech_duration: form.getFieldValue('vad_max_speech_duration'),
      });
      message.success('音频处理配置已保存');
    } catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingAudio(false); }
  };

  const handleResetVadDefaults = () => {
    form.setFieldsValue(DEFAULT_VAD_FORM_VALUES);
    setIsDirty(true);
    message.success('VAD 参数已恢复为默认值');
  };

  const handleSaveModels = async () => {
    try {
      setSavingModels(true);
      await api.config.partialUpdateConfig({
        enable_language_detection: !!form.getFieldValue('enable_language_detection'),
        lid_model_id: form.getFieldValue('lid_model_id') || null,
        lid_sample_duration: form.getFieldValue('lid_sample_duration') || 600,
        lid_num_segments: form.getFieldValue('lid_num_segments') || 3,
        lid_filter_whitelist_enabled: !!form.getFieldValue('lid_filter_whitelist_enabled'),
        lid_filter_whitelist: form.getFieldValue('lid_filter_whitelist') || [],
        asr_language_model_map: langModelMap,
        model_storage_dir: form.getFieldValue('model_storage_dir'),
        github_token: form.getFieldValue('github_token'),
      });
      message.success('模型配置已保存');
    } catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingModels(false); }
  };

  const handleSaveCleanup = async () => {
    try { setSavingCleanup(true); await api.config.partialUpdateConfig({ cleanup_temp_files_on_success: form.getFieldValue('cleanup_temp_files_on_success') }); message.success('清理配置已保存'); }
    catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingCleanup(false); }
  };

  const handleSaveTelegram = async () => {
    try {
      setSavingTelegram(true);
      await api.config.partialUpdateConfig({
        telegram_bot_token: form.getFieldValue('telegram_bot_token'),
        telegram_admin_ids: form.getFieldValue('telegram_admin_ids'),
        telegram_daily_task_limit: form.getFieldValue('telegram_daily_task_limit'),
        telegram_max_concurrent_per_user: form.getFieldValue('telegram_max_concurrent_per_user'),
        telegram_accessible_libraries: form.getFieldValue('telegram_accessible_libraries') || [],
      });
      message.success('Telegram 配置已保存');
    } catch (err: any) { message.error(err.message || '保存失败'); }
    finally { setSavingTelegram(false); }
  };

  const handleBotToggle = async () => {
    setBotLoading(true);
    try {
      if (botStatus?.running) {
        const r = await api.config.stopBot();
        setBotStatus({ running: r.running, uptime_seconds: r.uptime_seconds });
        message.success(r.message);
      } else {
        // 先保存配置再启动
        await api.config.partialUpdateConfig({
          telegram_bot_token: form.getFieldValue('telegram_bot_token'),
          telegram_admin_ids: form.getFieldValue('telegram_admin_ids'),
          telegram_daily_task_limit: form.getFieldValue('telegram_daily_task_limit'),
          telegram_max_concurrent_per_user: form.getFieldValue('telegram_max_concurrent_per_user'),
        });
        const r = await api.config.startBot();
        setBotStatus({ running: r.running, uptime_seconds: r.uptime_seconds });
        if (r.running) { message.success(r.message); } else { message.error(r.message); }
      }
    } catch (err: any) { message.error(err.message || '操作失败'); }
    finally { setBotLoading(false); }
  };

  const handleCleanupTemp = async () => {
    setCleaningTemp(true);
    try { const result = await api.config.cleanupTemp(); message.success(result.message); loadDiskUsage(); }
    catch (err: any) { message.error(err.message || '清理失败'); }
    finally { setCleaningTemp(false); }
  };

  const testEmby = async () => {
    setTestingEmby(true);
    try { await api.config.testEmby({ emby_url: form.getFieldValue('emby_url'), emby_api_key: form.getFieldValue('emby_api_key') }); message.success('Emby 节点连接成功'); }
    catch (err: any) { message.error(err.message || 'Emby 连接失败'); }
    finally { setTestingEmby(false); }
  };

  const testTranslation = async () => {
    setTestingTranslation(true);
    try {
      const service = form.getFieldValue('translation_service');
      const payload: any = { translation_service: service };
      if (service === 'openai') { payload.api_key = form.getFieldValue('openai_api_key'); payload.model = form.getFieldValue('openai_model'); payload.base_url = form.getFieldValue('openai_base_url'); }
      else if (service === 'deepseek') { payload.api_key = form.getFieldValue('deepseek_api_key'); }
      else if (service === 'local') { payload.api_url = form.getFieldValue('local_llm_url'); }
      else if (service === 'google') { payload.google_translate_mode = form.getFieldValue('google_translate_mode'); payload.api_key = form.getFieldValue('google_api_key'); }
      else if (service === 'microsoft') { payload.microsoft_translate_mode = form.getFieldValue('microsoft_translate_mode'); payload.api_key = form.getFieldValue('microsoft_api_key'); payload.microsoft_region = form.getFieldValue('microsoft_region'); }
      else if (service === 'baidu') { payload.baidu_app_id = form.getFieldValue('baidu_app_id'); payload.baidu_secret_key = form.getFieldValue('baidu_secret_key'); }
      else if (service === 'deepl') { payload.deepl_mode = form.getFieldValue('deepl_mode'); payload.api_key = form.getFieldValue('deepl_api_key'); payload.deeplx_url = form.getFieldValue('deeplx_url'); }
      await api.config.testTranslation(payload); message.success('翻译 API 通道畅通');
    } catch (err: any) { message.error(err.message || '翻译通道连接失败'); }
    finally { setTestingTranslation(false); }
  };

  const columns = [
    { title: '神经模型标识', dataIndex: 'name', key: 'name', render: (text: string, record: ASRModel) => (
      <Space>
        <Text strong style={{ color: 'var(--text-primary)' }}>{text}</Text>
        {record.active && <Tag color="success" style={{ background: 'var(--accent-emerald-bg)', border: '1px solid var(--accent-emerald)', color: 'var(--accent-emerald)' }}>当前激活</Tag>}
        {record.installed && !record.active && <Tag color="processing" style={{ background: 'var(--accent-cyan-bg)', border: '1px solid var(--accent-cyan)', color: 'var(--accent-cyan)' }}>就绪</Tag>}
      </Space>
    )},
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (type: string) => (
      <Tag color={type === 'online' ? 'blue' : 'green'} style={{ background: type === 'online' ? 'var(--accent-cyan-bg)' : 'var(--accent-emerald-bg)', border: 'none' }}>{type === 'online' ? '流式' : '离线'}</Tag>
    )},
    { title: '语言支持', dataIndex: 'languages', key: 'languages', render: (langs: string[]) => (langs || []).slice(0, 3).map(lang => <Tag key={lang} style={{ background: 'var(--bg-tag)', border: 'none', fontSize: 10 }}>{lang}</Tag>) },
    { title: '参数量', dataIndex: 'size', key: 'size', width: 100 },
    { title: '操作', key: 'action', width: 150, render: (_: any, record: ASRModel) => {
      if (record.installed) return (
        <Space size="middle">
          {!record.active && <Button type="link" onClick={() => api.models.activateModel(record.id).then(() => { loadModels(); loadConfig(); })} style={{ padding: 0, color: 'var(--accent-cyan)' }}>激活</Button>}
          <Popconfirm title="确认删除神经模型?" onConfirm={() => api.models.deleteModel(record.id).then(() => { loadModels(); loadConfig(); })}><Button type="link" danger style={{ padding: 0 }}>卸载</Button></Popconfirm>
        </Space>
      );
      const progress = downloadProgress[record.id];
      if (progress && (progress.status === 'downloading' || progress.status === 'extracting')) return (
        <div style={{ minWidth: 120 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <LoadingOutlined spin style={{ fontSize: 12, color: 'var(--accent-cyan)' }} />
            <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{progress.status === 'extracting' ? '解压中...' : progress.progress + '%'}</Text>
          </div>
          <Progress percent={progress.progress} size="small" showInfo={false} strokeColor="var(--accent-cyan)" trailColor="var(--glass-border)" />
        </div>
      );
      if (progress && progress.status === 'completed') return <Space><CheckCircleOutlined style={{ color: 'var(--accent-emerald)' }} /><Text style={{ color: 'var(--accent-emerald)', fontSize: 12 }}>下载完成</Text></Space>;
      if (progress && progress.status === 'failed') return <Space><Tooltip title={progress.error}><Button type="link" danger icon={<CloseCircleOutlined />} onClick={() => handleDownload(record.id)} style={{ padding: 0 }}>失败，重试</Button></Tooltip></Space>;
      return <Button type="link" icon={<DownloadOutlined />} onClick={() => handleDownload(record.id)} style={{ padding: 0, color: 'var(--accent-emerald)' }}>下载权重</Button>;
    }},
  ];

  const activeCat = CATEGORIES.find(c => c.key === activeCategory)!;

  const renderContent = () => {
    switch (activeCategory) {

      case 'emby': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">Emby 核心节点</h2>
              <p className="cat-sub">配置服务器地址与 API 密钥，建立与媒体库的连接</p>
            </div>
          </div>
          <div className="cat-section">
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="emby_url" label="服务器网络地址" rules={[{ required: true }]}><Input placeholder="http://localhost:8096" /></Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="emby_api_key" label={<Space>API 通行密钥 <Tooltip title="从 Emby 后台 → 设置 → API Keys 生成"><InfoCircleOutlined /></Tooltip></Space>} rules={[{ required: true }]}>
                  <Input.Password placeholder="输入您的 API Key" />
                </Form.Item>
              </Col>
            </Row>
          </div>
          <div className="cat-footer">
            <Space>
              <Button onClick={testEmby} loading={testingEmby}>测试连通性</Button>
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveEmby} loading={savingEmby} style={{ background: 'var(--accent-cyan)', borderColor: 'var(--accent-cyan)' }}>保存配置</Button>
            </Space>
          </div>
        </div>
      );

      case 'path': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">路径映射</h2>
              <p className="cat-sub">将 Emby 服务器视频路径映射为本地路径，用于字幕文件回写</p>
            </div>
          </div>
          <div className="cat-info-banner">
            <InfoCircleOutlined style={{ marginRight: 8, color: 'var(--accent-cyan)', flexShrink: 0 }} />
            <span>字幕生成完成后系统自动将 SRT 复制到视频同目录并刷新 Emby 元数据。支持跨平台路径转换：Emby（Linux）<code>/mnt/media</code> → 本地（Windows）<code>Z:\\Media</code>，自动转换分隔符。</span>
          </div>
          <div className="cat-section">
            <Form.List name="path_mappings">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <div key={key} className="mapping-row">
                      <Row gutter={12} align="top">
                        <Col span={5}>
                          <Form.Item {...restField} name={[name, 'name']} rules={[{ required: true, message: '请输入名称' }]} style={{ marginBottom: 0 }}>
                            <Input placeholder="规则名称" size="small" />
                          </Form.Item>
                        </Col>
                        <Col span={7}>
                          <Form.Item {...restField} name={[name, 'emby_prefix']} rules={[{ required: true, message: '请输入 Emby 路径前缀' }]} style={{ marginBottom: 0 }}>
                            <Input placeholder="Emby 路径，如 /mnt/media" size="small" />
                          </Form.Item>
                        </Col>
                        <Col span={7}>
                          <Form.Item {...restField} name={[name, 'local_prefix']} rules={[{ required: true, message: '请输入本地路径前缀' }]} style={{ marginBottom: 0 }}>
                            <Input placeholder="本地路径，如 Z:\\Media" size="small" />
                          </Form.Item>
                        </Col>
                        <Col span={4}>
                          <Form.Item {...restField} name={[name, 'library_ids']} initialValue={[]} style={{ marginBottom: 0 }}>
                            <Select mode="multiple" placeholder="关联媒体库" size="small" maxTagCount={1} allowClear>
                              {embyLibraries.map(lib => <Option key={lib.id} value={lib.id}>{lib.name}</Option>)}
                            </Select>
                          </Form.Item>
                        </Col>
                        <Col span={1} style={{ display: 'flex', justifyContent: 'center', paddingTop: 4 }}>
                          <Button type="text" danger icon={<DeleteOutlined />} size="small" onClick={() => remove(name)} />
                        </Col>
                      </Row>
                    </div>
                  ))}
                  <Button type="dashed" onClick={() => add({ name: '', emby_prefix: '', local_prefix: '', library_ids: [] })} block icon={<PlusOutlined />} style={{ borderColor: 'var(--glass-border)' }}>添加映射规则</Button>
                </>
              )}
            </Form.List>
          </div>
          <div className="cat-footer">
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveAll} loading={savingAll} style={{ background: 'var(--accent-amber)', borderColor: 'var(--accent-amber)' }}>保存所有配置</Button>
          </div>
        </div>
      );

      case 'translation': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">翻译服务</h2>
              <p className="cat-sub">选择翻译引擎并配置 API 凭证，决定字幕翻译的语言处理通道</p>
            </div>
          </div>
          <div className="cat-section">
            <Form.Item name="translation_service" label="主理翻译引擎">
              <Select dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}>
                <Option value="openai">OpenAI (GPT) <Tag color="processing" style={{ marginLeft: 8, border: 'none' }}>推荐</Tag></Option>
                <Option value="deepseek">DeepSeek AI</Option>
                <Option value="local">本地自定义模型 (LLM)</Option>
                <Option value="google">Google Translate</Option>
                <Option value="microsoft">Microsoft Translator</Option>
                <Option value="baidu">百度翻译</Option>
                <Option value="deepl">DeepL</Option>
              </Select>
            </Form.Item>
            <div className="engine-block">
              {translationService === 'openai' && (
                <Row gutter={24}>
                  <Col span={12}><Form.Item name="openai_api_key" label="OpenAI API Key" rules={[{ required: true }]}><Input.Password placeholder="sk-..." /></Form.Item></Col>
                  <Col span={12}><Form.Item name="openai_model" label="大语言模型" initialValue="gpt-4"><Input placeholder="gpt-4o / gpt-3.5-turbo" /></Form.Item></Col>
                </Row>
              )}
              {translationService === 'openai' && (
                <Form.Item name="openai_base_url" label="API Base URL" tooltip="自定义 OpenAI API 地址，支持中转站点或第三方服务" initialValue=""><Input placeholder="https://api.openai.com/v1 (留空使用官方地址)" /></Form.Item>
              )}
              {translationService === 'deepseek' && (<Form.Item name="deepseek_api_key" label="DeepSeek API Key" rules={[{ required: true }]}><Input.Password placeholder="sk-..." /></Form.Item>)}
              {translationService === 'local' && (<Form.Item name="local_llm_url" label="本地模型 Endpoint" rules={[{ required: true }]}><Input.Password placeholder="http://localhost:11434" /></Form.Item>)}
              {translationService === 'google' && (
                <Row gutter={24}>
                  <Col span={12}><Form.Item name="google_translate_mode" label="使用模式" initialValue="free"><Select><Option value="free">免费版</Option><Option value="api">官方 API</Option></Select></Form.Item></Col>
                  <Col span={12}><Form.Item name="google_api_key" label="API Key (API模式)" rules={[{ required: googleMode === 'api' }]}><Input.Password placeholder="仅 API 模式需要" /></Form.Item></Col>
                </Row>
              )}
              {translationService === 'microsoft' && (
                <Row gutter={24}>
                  <Col span={8}><Form.Item name="microsoft_translate_mode" label="使用模式" initialValue="free"><Select><Option value="free">免费版</Option><Option value="api">官方 API</Option></Select></Form.Item></Col>
                  <Col span={8}><Form.Item name="microsoft_api_key" label="API Key" rules={[{ required: microsoftMode === 'api' }]}><Input.Password placeholder="仅 API 模式需要" /></Form.Item></Col>
                  <Col span={8}><Form.Item name="microsoft_region" label="区域" initialValue="global"><Input placeholder="global / eastasia" /></Form.Item></Col>
                </Row>
              )}
              {translationService === 'baidu' && (
                <Row gutter={24}>
                  <Col span={12}><Form.Item name="baidu_app_id" label="百度 APP ID" rules={[{ required: true }]}><Input placeholder="从百度翻译开放平台获取" /></Form.Item></Col>
                  <Col span={12}><Form.Item name="baidu_secret_key" label="Secret Key" rules={[{ required: true }]}><Input.Password placeholder="密钥" /></Form.Item></Col>
                </Row>
              )}
              {translationService === 'deepl' && (
                <Row gutter={24}>
                  <Col span={8}><Form.Item name="deepl_mode" label="使用模式" initialValue="deeplx"><Select><Option value="deeplx">DeepLX (免费)</Option><Option value="api">官方 API</Option></Select></Form.Item></Col>
                  <Col span={8}><Form.Item name="deepl_api_key" label="API Key" rules={[{ required: deeplMode === 'api' }]}><Input.Password placeholder="仅 API 模式需要" /></Form.Item></Col>
                  <Col span={8}><Form.Item name="deeplx_url" label="DeepLX 地址" rules={[{ required: deeplMode === 'deeplx' }]}><Input placeholder="http://localhost:1188" /></Form.Item></Col>
                </Row>
              )}
            </div>
            <Row gutter={24} style={{ marginTop: 16 }}>
              <Col span={12}>
                <Form.Item
                  name="translation_concurrency"
                  label={
                    <Space>
                      翻译并发数
                      <Tooltip title="同一任务内并发调用翻译接口的最大数量。留空使用各 provider 的推荐值（OpenAI/DeepSeek=8, Google/Microsoft 免费=2, 本地 LLM=2, DeepL=4）。百度翻译因 1 QPS 硬限制强制串行，此项无效。并发不会打乱字幕顺序。">
                        <InfoCircleOutlined />
                      </Tooltip>
                    </Space>
                  }
                >
                  <InputNumber
                    min={1}
                    max={32}
                    placeholder="留空 = 使用默认值"
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="translation_context_size"
                  label={
                    <Space>
                      上下文窗口
                      <Tooltip title="翻译时提供当前字幕前后各 N 条作为上下文参考，提高翻译连贯性。仅对 LLM 翻译器（OpenAI/DeepSeek/本地LLM）有效，传统 API 翻译器会忽略此设置。0 = 禁用。推荐值: 2-5。">
                        <InfoCircleOutlined />
                      </Tooltip>
                    </Space>
                  }
                >
                  <InputNumber
                    min={0}
                    max={10}
                    placeholder="0 = 禁用"
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </Col>
            </Row>
          </div>
          <div className="cat-footer">
            <Space>
              <Button onClick={testTranslation} loading={testingTranslation}>测试通道</Button>
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveTranslation} loading={savingTranslation} style={{ background: 'var(--accent-emerald)', borderColor: 'var(--accent-emerald)' }}>保存配置</Button>
            </Space>
          </div>
        </div>
      );

      case 'asr': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">ASR 引擎</h2>
              <p className="cat-sub">选择语音识别推理引擎，配置本地模型或云端 API</p>
            </div>
          </div>
          <div className="cat-section">
            <Form.Item name="asr_engine" label="默认推理引擎">
              <Select dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                <Option value="sherpa-onnx">本地模型 (Sherpa ONNX)</Option>
                <Option value="cloud">云端 API</Option>
              </Select>
            </Form.Item>
            <div className="engine-block local">
              <div className="engine-label"><RocketOutlined style={{ marginRight: 6 }} />本地模型配置</div>
              <Row gutter={24}>
                <Col span={16}>
                  <Form.Item name="asr_model_id" label="已激活模型">
                    <Select placeholder="请先下载并激活模型" disabled dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                      {models.filter(m => m.installed).map(m => <Option key={m.id} value={m.id}>{m.name} {m.active && <Tag color="success" style={{ marginLeft: 8 }}>当前激活</Tag>}</Option>)}
                    </Select>
                  </Form.Item>
                  <Text type="secondary" style={{ fontSize: 12 }}>在「模型管理」中下载并激活模型后自动应用</Text>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_concurrent_tasks" label="并行处理线程数" tooltip="修改并保存后会自动重启 Celery Worker"><InputNumber min={1} max={16} style={{ width: '100%' }} /></Form.Item>
                </Col>
              </Row>
            </div>
            <div className="engine-block cloud">
              <div className="engine-label"><CloudServerOutlined style={{ marginRight: 6 }} />云端厂商配置</div>
              <Row gutter={24}>
                <Col span={8}>
                  <Form.Item name="cloud_asr_provider" label="云端厂商" initialValue="groq">
                    <Select dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                      <Option value="groq">Groq</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="groq_asr_model" label="Groq 模型" initialValue="whisper-large-v3-turbo">
                    <Select dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                      <Option value="whisper-large-v3-turbo">whisper-large-v3-turbo</Option>
                      <Option value="whisper-large-v3">whisper-large-v3</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="groq_asr_api_key" label="Groq API Key">
                    <Input.Password placeholder="gsk_..." />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item name="groq_asr_base_url" label="Groq Base URL" initialValue="https://api.groq.com/openai/v1">
                    <Input placeholder="https://api.groq.com/openai/v1" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="groq_asr_public_audio_base_url" label="公网音频访问地址">
                    <Input placeholder="https://subtitle.790366.xyz" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item name="groq_asr_prompt" label="识别 Prompt">
                    <Input placeholder="可选：提供专有名词、角色名或上下文提示" />
                  </Form.Item>
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 12 }}>公网音频访问地址用于大于 24MB 的 FLAC 音频，系统会生成短期签名 URL 供 Groq 拉取；留空时自动回退本地切片。</Text>
            </div>
          </div>
          <div className="cat-footer">
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveAsr} loading={savingAsr} style={{ background: 'var(--accent-amber)', borderColor: 'var(--accent-amber)' }}>保存配置</Button>
          </div>
        </div>
      );

      case 'language': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">语言与字幕</h2>
              <p className="cat-sub">配置音频源语言、字幕目标语言和语言检测策略</p>
            </div>
          </div>
          <div className="cat-section">
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="source_language" label="源语言（音频语言）">
                  <Select placeholder="选择源语言" dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                    {languages.map(lang => <Option key={lang.code} value={lang.code}>{lang.name} ({lang.code})</Option>)}
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="target_languages"
                  label={
                    <Space>
                      目标语言（字幕语言）
                      <Tooltip title="可多选：同时生成多份字幕。第一个语言为主目标（默认展示），所有语言都会复制到视频目录。">
                        <InfoCircleOutlined />
                      </Tooltip>
                    </Space>
                  }
                >
                  <Select mode="multiple" placeholder="选择目标语言（可多选）" dropdownStyle={{ background: 'var(--bg-elevated)' }} allowClear>
                    {languages.map(lang => <Option key={lang.code} value={lang.code}>{lang.name} ({lang.code})</Option>)}
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <div style={{ padding: 12, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)', marginBottom: 16 }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, color: 'var(--text-primary)' }}>
                    <InfoCircleOutlined style={{ color: 'var(--accent-cyan)' }} />保留源语言字幕
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    除目标语言字幕外，额外输出一份未经翻译的源语言字幕文件（使用 ASR 原文）。
                  </Text>
                </Col>
                <Col>
                  <Form.Item name="keep_source_subtitle" valuePropName="checked" style={{ margin: 0 }}>
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
            </div>
            <Form.Item
              name="source_language_detection"
              label={
                <Space>
                  源语言检测模式
                  <Tooltip title="Auto 模式：翻译时自动检测实际语言（推荐）。Fixed 模式：强制使用配置的源语言。">
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              }
              initialValue="auto"
            >
              <Select dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                <Option value="auto">
                  <Space>
                    自动检测 (Auto)
                    <Tag color="success" style={{ marginLeft: 4, border: 'none' }}>推荐</Tag>
                  </Space>
                </Option>
                <Option value="fixed">固定语言 (Fixed)</Option>
              </Select>
            </Form.Item>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: -16, marginBottom: 16 }}>
              • Auto 模式：翻译服务自动检测 ASR 输出的实际语言，适用于多语言视频或不确定语言的场景<br />
              • Fixed 模式：强制使用配置的源语言，适用于确定所有视频都是同一语言的场景
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>源语言与目标语言相同时将跳过翻译步骤，仅生成转录字幕</Text>
            <div style={{ marginTop: 16, padding: 12, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)' }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, color: 'var(--text-primary)' }}>
                    <FilterOutlined style={{ color: 'var(--accent-amber)' }} />语气词过滤
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>移除纯语气词段落（あ、え、うん 等），减少无意义翻译，节省 token 开销</Text>
                </Col>
                <Col><Form.Item name="filter_filler_words" valuePropName="checked" style={{ margin: 0 }}><Switch /></Form.Item></Col>
              </Row>
              {filterFillerWords && (
                <div style={{ marginTop: 12 }}>
                  <Form.Item
                    name="custom_filler_words"
                    label={
                      <Space>
                        自定义语气词
                        <Tooltip title="输入后按回车添加。此处添加的词会与内置词表合并生效。">
                          <InfoCircleOutlined />
                        </Tooltip>
                      </Space>
                    }
                    style={{ marginBottom: 8 }}
                  >
                    <Select mode="tags" placeholder="输入语气词后按回车添加（可选）" tokenSeparators={[',', '，', ' ']} dropdownStyle={{ display: 'none' }} style={{ width: '100%' }} />
                  </Form.Item>
                  {defaultFillerWords['ja'] && (
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>已内置 {defaultFillerWords['ja'].length} 个日语语气词：</Text>
                      <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {defaultFillerWords['ja'].map(w => (
                          <Tag key={w} style={{ background: 'var(--bg-tag)', border: 'none', fontSize: 11, margin: 0 }}>{w}</Tag>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="cat-footer">
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveLanguage} loading={savingLanguage} style={{ background: 'var(--accent-cyan)', borderColor: 'var(--accent-cyan)' }}>保存配置</Button>
          </div>
        </div>
      );

      case 'audio': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">音频处理</h2>
              <p className="cat-sub">配置音频降噪与 VAD 分段，优化语音识别效果</p>
            </div>
          </div>
          <div className="cat-section">
            <div style={{ padding: 12, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)', marginBottom: 16 }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, color: 'var(--text-primary)' }}>
                    <InfoCircleOutlined style={{ color: 'var(--accent-cyan)' }} />音频降噪 (Denoise)
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>启用后使用频谱门控算法降低背景噪声，提升嘈杂场景下的识别准确率（建议配合 VAD 使用）</Text>
                </Col>
                <Col><Form.Item name="enable_denoise" valuePropName="checked" style={{ margin: 0 }}><Switch /></Form.Item></Col>
              </Row>
            </div>
            <div style={{ padding: 12, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)' }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, color: 'var(--text-primary)' }}>
                    <InfoCircleOutlined style={{ color: 'var(--accent-amber)' }} />语音活动检测 (VAD)
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>启用后对音频进行分段处理，获得更精确的字幕时间戳（仅离线模型有效）</Text>
                </Col>
                <Col><Form.Item name="enable_vad" valuePropName="checked" style={{ margin: 0 }}><Switch /></Form.Item></Col>
              </Row>
              {enableVad && (
                <div style={{ marginTop: 12 }}>
                  <Form.Item name="vad_mode" label="分段模式" style={{ marginBottom: 12 }}>
                    <Radio.Group>
                      <Radio.Button value="energy">能量分段（推荐）</Radio.Button>
                      <Radio.Button value="silero">Silero VAD</Radio.Button>
                    </Radio.Group>
                  </Form.Item>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: -4, marginBottom: 12 }}>
                    <Button icon={<ReloadOutlined />} onClick={handleResetVadDefaults}>
                      恢复默认值
                    </Button>
                  </div>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: -8, marginBottom: 12 }}>
                    {vadMode === 'silero'
                      ? '• Silero VAD：使用神经网络检测语音段，精确但较慢，可能在嘈杂场景漏检'
                      : '• 能量分段：按静音位置切分音频，速度极快，不做语音判断不会漏检（建议配合降噪使用）'}
                  </Text>
                  {vadMode === 'silero' && (
                    <>
                      <Row gutter={24}>
                        <Col span={16}>
                          <Form.Item name="vad_model_id" label="VAD 模型">
                            <Select placeholder={vadModels.filter(m => m.installed).length ? '选择 VAD 模型' : '请先下载 VAD 模型'} dropdownStyle={{ background: 'var(--bg-elevated)' }} loading={vadModelsLoading} disabled={!vadModels.some(m => m.installed)}>
                              {vadModels.filter(m => m.installed).map(m => <Option key={m.id} value={m.id}>{m.name} {m.active && <Tag color="success" style={{ marginLeft: 8 }}>激活</Tag>}</Option>)}
                            </Select>
                          </Form.Item>
                        </Col>
                        <Col span={8}>
                          <Form.Item label=" "><Button onClick={loadVadModels} loading={vadModelsLoading} icon={<ReloadOutlined />} type="text" size="small">刷新</Button></Form.Item>
                        </Col>
                      </Row>
                      {vadModelsLoading ? (
                        <div style={{ textAlign: 'center', padding: 16 }}><LoadingOutlined spin style={{ fontSize: 20, color: 'var(--accent-cyan)' }} /><div style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 12 }}>加载中...</div></div>
                      ) : vadModels.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                          {vadModels.map(m => {
                            const progress = downloadProgress[m.id];
                            const isDownloading = progress && (progress.status === 'downloading' || progress.status === 'extracting');
                            return (
                              <div key={m.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--glass-border)' }}>
                                <Space>
                                  <Text style={{ color: 'var(--text-primary)' }}>{m.name}</Text>
                                  <Tag style={{ background: 'var(--bg-tag)', border: 'none', fontSize: 10 }}>{m.size}</Tag>
                                  {m.installed && <Tag color="success" style={{ background: 'var(--accent-emerald-bg)', border: '1px solid var(--accent-emerald)', color: 'var(--accent-emerald)' }}>已安装</Tag>}
                                </Space>
                                <Space>
                                  {isDownloading ? (
                                    <Space size={4}><LoadingOutlined spin style={{ fontSize: 12, color: 'var(--accent-cyan)' }} /><Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{progress.progress}%</Text></Space>
                                  ) : m.installed ? (
                                    <Button type="link" size="small" onClick={() => api.models.activateVadModel(m.id).then(() => { loadVadModels(); loadConfig(); })} style={{ padding: 0, color: 'var(--accent-cyan)' }}>{m.active ? '已激活' : '激活'}</Button>
                                  ) : (
                                    <Button type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleVadDownload(m.id)} style={{ padding: 0, color: 'var(--accent-emerald)' }}>下载</Button>
                                  )}
                                </Space>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </>
                  )}
                  <Collapse ghost size="small" items={[{
                    key: 'vad-advanced',
                    label: <Text type="secondary" style={{ fontSize: 12 }}>高级参数</Text>,
                    children: (
                      <>
                        {vadMode === 'silero' && (
                          <Row gutter={24}>
                            <Col span={12}><Form.Item name="vad_threshold" label="语音检测阈值"><Slider min={0.1} max={0.9} step={0.05} marks={{ 0.2: '0.2', 0.5: '0.5', 0.8: '0.8' }} /></Form.Item></Col>
                            <Col span={12}><Form.Item name="vad_max_speech_duration" label="最大语音段长度 (秒)"><InputNumber min={1} max={60} step={1} style={{ width: '100%' }} /></Form.Item></Col>
                          </Row>
                        )}
                        {vadMode !== 'silero' && (
                          <Row gutter={24}>
                            <Col span={12}><Form.Item name="vad_max_speech_duration" label="最大语音段长度 (秒)"><InputNumber min={1} max={60} step={1} style={{ width: '100%' }} /></Form.Item></Col>
                          </Row>
                        )}
                        <Row gutter={24}>
                          <Col span={12}><Form.Item name="vad_min_silence_duration" label="最小静音时长 (秒)"><InputNumber min={0.1} max={5} step={0.1} style={{ width: '100%' }} /></Form.Item></Col>
                          <Col span={12}><Form.Item name="vad_min_speech_duration" label="最小语音时长 (秒)"><InputNumber min={0.05} max={5} step={0.05} style={{ width: '100%' }} /></Form.Item></Col>
                        </Row>
                      </>
                    ),
                  }]} />
                </div>
              )}
            </div>
          </div>
          <div className="cat-footer">
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveAudio} loading={savingAudio} style={{ background: 'var(--accent-emerald)', borderColor: 'var(--accent-emerald)' }}>保存配置</Button>
          </div>
        </div>
      );

      case 'models': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">模型管理</h2>
              <p className="cat-sub">下载、激活 ASR 模型，配置语言自适应映射</p>
            </div>
          </div>
          <div className="cat-section">
            <div style={{ padding: '16px 24px', marginBottom: 16, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)' }}>
              <Row gutter={12}>
                <Col flex="auto"><Input placeholder="搜索模型名称..." allowClear value={modelSearch} onChange={e => setModelSearch(e.target.value)} /></Col>
                <Col flex="180px">
                  <Select placeholder="按语言筛选" allowClear value={modelLangFilter} onChange={v => setModelLangFilter(v)} style={{ width: '100%' }} dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}>
                    {availableLanguages.map(lang => <Option key={lang} value={lang}>{lang}</Option>)}
                  </Select>
                </Col>
              </Row>
            </div>
            <Table columns={columns} dataSource={filteredModels} rowKey="id" pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (total) => '共 ' + total + ' 个模型', style: { marginRight: 16 } }} loading={modelsLoading} className="custom-table" style={{ background: 'transparent' }} />
            <div className="engine-block local" style={{ marginTop: 16 }}>
              <div className="engine-label"><AimOutlined style={{ marginRight: 6 }} />语言检测与自适应模型</div>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
                启用后，任务执行时先用 Whisper 检测音频语言，再按映射自动切换 ASR 模型。适合媒体库含多种语言的场景。
              </Text>
              <Row gutter={24} align="middle">
                <Col span={4}>
                  <Form.Item name="enable_language_detection" valuePropName="checked" style={{ marginBottom: 8 }}>
                    <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                  </Form.Item>
                </Col>
                <Col span={10}>
                  <Form.Item name="lid_model_id" label="LID 检测模型" tooltip="用于语言检测的 Whisper 模型，推荐 whisper-tiny（轻量快速）">
                    <Select placeholder="选择已下载的 Whisper 模型" allowClear disabled={!enableLangDetection} dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}>
                      {models.filter(m => m.installed && m.model_type === 'whisper').map(m => (
                        <Option key={m.id} value={m.id}>{m.name} ({m.size})</Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={5}>
                  <Form.Item name="lid_sample_duration" label="扫描时长 (秒)" tooltip="在音频前 N 秒范围内寻找有声片段进行语言检测。长影片建议 600 秒以跳过 OP 音乐">
                    <InputNumber min={30} max={1800} step={30} style={{ width: '100%' }} disabled={!enableLangDetection} />
                  </Form.Item>
                </Col>
                <Col span={5}>
                  <Form.Item name="lid_num_segments" label="采样段数" tooltip="从有声区域中均匀选取多少段分别检测，投票决定最终语言。段数越多越准确但耗时更长，建议 5-10 段">
                    <InputNumber min={1} max={15} step={1} style={{ width: '100%' }} disabled={!enableLangDetection} />
                  </Form.Item>
                </Col>
              </Row>
              {enableLangDetection && (
                <>
                  <div style={{ marginTop: 4, marginBottom: 16, padding: 12, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)' }}>
                    <Row align="middle" gutter={16}>
                      <Col flex="auto">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, color: 'var(--text-primary)' }}>
                          <FilterOutlined style={{ color: 'var(--accent-rose)' }} />语言白名单过滤
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          开启后，LID 投票结果会按票数排序，若第一名不在白名单内则顺延选择下一名；若所有候选都不在白名单中，则本次语言检测视为无结果并回退默认源语言配置。
                        </Text>
                      </Col>
                      <Col>
                        <Form.Item name="lid_filter_whitelist_enabled" valuePropName="checked" style={{ margin: 0 }}>
                          <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                        </Form.Item>
                      </Col>
                    </Row>
                    <Form.Item
                      name="lid_filter_whitelist"
                      label="允许的检测语言"
                      tooltip="建议只保留媒体库里真实可能出现的语言，减少 nn 等小众误判对后续 ASR 选择的影响。"
                      style={{ marginTop: 12, marginBottom: 0 }}
                    >
                      <Select
                        mode="multiple"
                        allowClear
                        placeholder="选择允许作为最终检测结果的语言"
                        disabled={!enableLidWhitelistFilter}
                        dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}
                      >
                        {languages.map(lang => (
                          <Option key={lang.code} value={lang.code}>{lang.name} ({lang.code})</Option>
                        ))}
                      </Select>
                    </Form.Item>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                      白名单关闭或留空时，不额外过滤，保持现有投票结果。
                    </Text>
                  </div>
                  <div style={{ marginTop: 8, marginBottom: 8 }}>
                    <Text strong style={{ fontSize: 13 }}>语言 → 模型映射</Text>
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>未映射的语言使用上方激活的默认模型</Text>
                  </div>
                  {Object.entries(langModelMap).map(([lang, modelId]) => (
                    <Row key={lang} gutter={12} align="middle" style={{ marginBottom: 8 }}>
                      <Col span={6}>
                        <Select
                          value={lang}
                          style={{ width: '100%' }}
                          dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}
                          onChange={(newLang) => {
                            const updated = { ...langModelMap };
                            delete updated[lang];
                            updated[newLang] = modelId;
                            setLangModelMap(updated);
                            setIsDirty(true);
                          }}
                        >
                          {languages.map(l => (
                            <Option key={l.code} value={l.code} disabled={l.code !== lang && langModelMap.hasOwnProperty(l.code)}>{l.name} ({l.code})</Option>
                          ))}
                        </Select>
                      </Col>
                      <Col span={2} style={{ textAlign: 'center' }}>
                        <Text type="secondary">→</Text>
                      </Col>
                      <Col span={13}>
                        <Select
                          value={modelId}
                          style={{ width: '100%' }}
                          dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}
                          placeholder="选择已下载的 ASR 模型"
                          onChange={(newModel) => {
                            setLangModelMap({ ...langModelMap, [lang]: newModel });
                            setIsDirty(true);
                          }}
                        >
                          {models.filter(m => m.installed).map(m => (
                            <Option key={m.id} value={m.id}>{m.name} ({m.languages.join(', ')})</Option>
                          ))}
                        </Select>
                      </Col>
                      <Col span={2}>
                        <Button
                          icon={<DeleteOutlined />}
                          type="text"
                          danger
                          onClick={() => {
                            const updated = { ...langModelMap };
                            delete updated[lang];
                            setLangModelMap(updated);
                            setIsDirty(true);
                          }}
                        />
                      </Col>
                    </Row>
                  ))}
                  <Button
                    icon={<PlusOutlined />}
                    type="dashed"
                    block
                    style={{ marginTop: 4 }}
                    onClick={() => {
                      const usedLangs = new Set(Object.keys(langModelMap));
                      const nextLang = languages.find(l => !usedLangs.has(l.code));
                      if (nextLang) {
                        setLangModelMap({ ...langModelMap, [nextLang.code]: '' });
                        setIsDirty(true);
                      } else {
                        message.warning('所有语言已添加映射');
                      }
                    }}
                  >
                    添加语言映射
                  </Button>
                </>
              )}
            </div>
            <div className="engine-block local" style={{ marginTop: 16 }}>
              <div className="engine-label"><CloudServerOutlined style={{ marginRight: 6 }} />模型存储配置</div>
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item name="model_storage_dir" label="模型存储目录" tooltip="ASR/VAD 模型的本地存储路径，留空使用默认路径 ./data/models">
                    <Input placeholder="./data/models" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="github_token" label="GitHub Token" tooltip="可选，用于提高模型下载 API 速率限制（匿名 60次/小时 → 认证 5000次/小时）">
                    <Input.Password placeholder="ghp_xxxxxxxxxxxx" visibilityToggle />
                  </Form.Item>
                </Col>
              </Row>
            </div>
          </div>
          <div className="cat-footer">
            <Space>
              <Button icon={<ReloadOutlined />} onClick={async () => { setModelsLoading(true); try { const data = await api.models.refreshModels(); setModels(data); } catch {} finally { setModelsLoading(false); } loadVadModels(); }} loading={modelsLoading} type="text">刷新模型列表</Button>
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveModels} loading={savingModels} style={{ background: 'var(--accent-rose)', borderColor: 'var(--accent-rose)' }}>保存配置</Button>
            </Space>
          </div>
        </div>
      );

      case 'worker': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">任务 Worker</h2>
              <p className="cat-sub">后台字幕生成进程，由主后端托管启动。修改并发数后会自动重启以应用新配置</p>
            </div>
          </div>
          <div className="cat-section">
            <div style={{ marginBottom: 20, padding: 16, background: 'var(--bg-input)', borderRadius: 10, border: '1px solid var(--glass-border)' }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: workerStatus?.running ? '#22c55e' : '#6b7280', boxShadow: workerStatus?.running ? '0 0 8px #22c55e' : 'none' }} />
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 15 }}>
                      {workerStatus?.running ? 'Worker 运行中' : 'Worker 未运行'}
                    </span>
                    {workerStatus?.running && (
                      <Tag color="success" style={{ marginLeft: 4 }}>PID {workerStatus.pid ?? '-'}</Tag>
                    )}
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {workerStatus?.running
                      ? `已运行 ${workerStatus.uptime_seconds != null
                          ? (workerStatus.uptime_seconds >= 3600
                              ? Math.floor(workerStatus.uptime_seconds / 3600) + ' 小时 ' + Math.floor((workerStatus.uptime_seconds % 3600) / 60) + ' 分钟'
                              : workerStatus.uptime_seconds >= 60
                                ? Math.floor(workerStatus.uptime_seconds / 60) + ' 分钟 ' + (workerStatus.uptime_seconds % 60) + ' 秒'
                                : workerStatus.uptime_seconds + ' 秒')
                          : '-'}`
                      : '后台 Worker 未启动，字幕任务不会被处理'}
                  </Text>
                </Col>
                <Col>
                  <Space>
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      disabled={workerStatus?.running}
                      loading={workerLoading}
                      onClick={() => handleWorkerAction('start')}
                      style={!workerStatus?.running ? { background: 'var(--accent-emerald)', borderColor: 'var(--accent-emerald)' } : {}}
                    >
                      启动
                    </Button>
                    <Button
                      icon={<SyncOutlined />}
                      disabled={!workerStatus?.running}
                      loading={workerLoading}
                      onClick={() => handleWorkerAction('restart')}
                    >
                      重启
                    </Button>
                    <Button
                      danger
                      icon={<CloseCircleOutlined />}
                      disabled={!workerStatus?.running}
                      loading={workerLoading}
                      onClick={() => handleWorkerAction('stop')}
                    >
                      停止
                    </Button>
                  </Space>
                </Col>
              </Row>
            </div>

            <div className="cat-info-banner" style={{ marginBottom: 16 }}>
              <InfoCircleOutlined style={{ marginRight: 8 }} />
              <span>主后端启动时会自动拉起 Worker；保存"并行处理线程数"后会自动重启生效。如 Worker 异常退出，可在此手动启动。</span>
            </div>

            <Row gutter={24}>
              <Col span={8}>
                <Form.Item name="max_concurrent_tasks" label="并行处理线程数" tooltip="Worker 同时处理的任务数，1-16，修改后保存会自动重启 Worker">
                  <InputNumber min={1} max={16} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
          </div>
          <div className="cat-footer">
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveAsr} loading={savingAsr} style={{ background: 'var(--accent-emerald)', borderColor: 'var(--accent-emerald)' }}>
              保存并应用
            </Button>
          </div>
        </div>
      );

      case 'telegram': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">Telegram 机器人</h2>
              <p className="cat-sub">配置 Bot Token、管理员和用户配额，通过 Telegram 发起字幕任务</p>
            </div>
          </div>
          <div className="cat-section">
            {/* Bot 运行状态 */}
            <div style={{ marginBottom: 20, padding: 14, background: 'var(--bg-input)', borderRadius: 8, border: '1px solid var(--glass-border)' }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: botStatus?.running ? '#22c55e' : '#6b7280' }} />
                    <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                      {botStatus?.running ? 'Bot 运行中' : 'Bot 未启动'}
                    </span>
                    {botStatus?.running && botStatus.uptime_seconds != null && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        已运行 {botStatus.uptime_seconds >= 3600
                          ? Math.floor(botStatus.uptime_seconds / 3600) + '小时'
                          : botStatus.uptime_seconds >= 60
                            ? Math.floor(botStatus.uptime_seconds / 60) + '分钟'
                            : Math.floor(botStatus.uptime_seconds) + '秒'}
                      </Text>
                    )}
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {botStatus?.running
                      ? '点击停止按钮可关闭 Bot，配置修改后需重启生效'
                      : '填写 Token 后点击启动按钮开启 Bot 服务'}
                  </Text>
                </Col>
                <Col>
                  <Button
                    type={botStatus?.running ? 'default' : 'primary'}
                    danger={botStatus?.running}
                    loading={botLoading}
                    onClick={handleBotToggle}
                    icon={botStatus?.running ? <CloseCircleOutlined /> : <RocketOutlined />}
                    style={!botStatus?.running ? { background: 'var(--accent-cyan)', borderColor: 'var(--accent-cyan)' } : {}}
                  >
                    {botStatus?.running ? '停止 Bot' : '启动 Bot'}
                  </Button>
                </Col>
              </Row>
            </div>

            <div className="cat-info-banner" style={{ marginBottom: 16 }}>
              <InfoCircleOutlined style={{ marginRight: 8 }} />
              <span>从 <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> 创建 Bot 并获取 Token，启用内联模式请使用 /setinline 命令。</span>
            </div>
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="telegram_bot_token" label="Bot Token"><Input.Password placeholder="123456789:ABCdefGHIjklmnoPQRstUVwxyz..." /></Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="telegram_admin_ids" label="管理员 Telegram ID" tooltip="逗号分隔多个 ID，可通过 @userinfobot 获取"><Input placeholder="123456789,987654321" /></Form.Item>
              </Col>
            </Row>
            <div style={{ marginTop: 8, marginBottom: 8, fontWeight: 500, color: 'var(--text-primary)' }}>配额控制</div>
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="telegram_daily_task_limit" label="每用户每日任务上限" tooltip="每个用户每天最多可提交的字幕生成任务数">
                  <InputNumber min={1} max={100} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="telegram_max_concurrent_per_user" label="每用户最大并发任务" tooltip="每个用户同时进行中的任务数上限">
                  <InputNumber min={1} max={10} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>

            <div style={{ marginTop: 8, marginBottom: 8, fontWeight: 500, color: 'var(--text-primary)' }}>媒体库访问控制</div>
            <div className="cat-info-banner" style={{ marginBottom: 12 }}>
              <InfoCircleOutlined style={{ marginRight: 8 }} />
              <span>勾选允许 Telegram BOT 用户访问的媒体库。<b>留空表示允许所有媒体库（向后兼容）</b>。未勾选的媒体库对 BOT 用户完全不可见。</span>
            </div>
            <Form.Item noStyle shouldUpdate={(prev, cur) => prev.telegram_accessible_libraries !== cur.telegram_accessible_libraries}>
              {() => {
                const selected: string[] = form.getFieldValue('telegram_accessible_libraries') || [];
                const allIds = embyLibraries.map(l => l.id);
                return (
                  <div>
                    <Space style={{ marginBottom: 8 }}>
                      <Button size="small" onClick={() => { form.setFieldValue('telegram_accessible_libraries', allIds); setIsDirty(true); }}>全选</Button>
                      <Button size="small" onClick={() => { form.setFieldValue('telegram_accessible_libraries', []); setIsDirty(true); }}>全不选</Button>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        已选择 {selected.length} / {embyLibraries.length} 个媒体库
                        {selected.length === 0 && '（留空 = 允许所有）'}
                      </Text>
                    </Space>
                    <Form.Item name="telegram_accessible_libraries" noStyle>
                      <Checkbox.Group style={{ width: '100%' }}>
                        <Row gutter={[8, 8]}>
                          {embyLibraries.length === 0 && (
                            <Col span={24}><Text type="secondary">暂无可用媒体库，请先配置 Emby 并确保连接正常</Text></Col>
                          )}
                          {embyLibraries.map(lib => (
                            <Col key={lib.id} span={8}>
                              <Checkbox value={lib.id}>{lib.name}</Checkbox>
                            </Col>
                          ))}
                        </Row>
                      </Checkbox.Group>
                    </Form.Item>
                  </div>
                );
              }}
            </Form.Item>
          </div>
          <div className="cat-footer">
            <Space>
              <Button icon={<ReloadOutlined />} onClick={loadBotStatus} type="text">刷新状态</Button>
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveTelegram} loading={savingTelegram} style={{ background: 'var(--accent-cyan)', borderColor: 'var(--accent-cyan)' }}>保存配置</Button>
            </Space>
          </div>
        </div>
      );

      case 'cleanup': return (
        <div className="cat-panel">
          <div className="cat-hero">
            <div className="cat-icon" style={{ background: 'var(' + activeCat.colorBgVar + ')', color: 'var(' + activeCat.colorVar + ')' }}>{activeCat.icon}</div>
            <div>
              <h2 className="cat-title">临时文件管理</h2>
              <p className="cat-sub">配置临时文件清理策略，管理磁盘占用</p>
            </div>
          </div>
          <div className="cat-section">
            <div style={{ marginBottom: 20, padding: 14, background: 'var(--bg-input)', borderRadius: 8, border: '1px solid var(--glass-border)' }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>任务成功后自动清理临时文件</div>
                  <Text type="secondary" style={{ fontSize: 12 }}>开启后，字幕生成成功时自动删除音频提取、ASR 中间结果等临时文件。关闭则保留所有中间产物，方便调试排查问题。</Text>
                </Col>
                <Col><Form.Item name="cleanup_temp_files_on_success" valuePropName="checked" style={{ margin: 0 }}><Switch /></Form.Item></Col>
              </Row>
            </div>
            <div style={{ padding: 14, background: 'var(--bg-input)', borderRadius: 8, border: '1px solid var(--glass-border)' }}>
              <Row align="middle" justify="space-between" style={{ marginBottom: 12 }}>
                <Col>
                  <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>手动清理所有临时文件</div>
                  <Text type="secondary" style={{ fontSize: 12 }}>立即删除 data/tasks/ 下所有任务目录（包括失败任务的中间产物）</Text>
                </Col>
                <Col>
                  <Space>
                    {diskUsage !== null && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        当前占用：<span style={{ color: diskUsage.total_mb > 500 ? '#ef4444' : 'var(--accent-cyan)', fontWeight: 600 }}>{diskUsage.total_mb} MB</span>
                        &nbsp;({diskUsage.task_count} 个任务目录)
                      </Text>
                    )}
                    <Button icon={<ReloadOutlined />} size="small" type="text" onClick={loadDiskUsage} style={{ color: 'var(--text-secondary)' }} />
                  </Space>
                </Col>
              </Row>
              <Popconfirm title="确认清理所有临时文件？" description="此操作不可撤销，将删除所有任务的中间产物（音频、ASR 结果等）" onConfirm={handleCleanupTemp} okText="确认清理" cancelText="取消" okButtonProps={{ danger: true }}>
                <Button danger loading={cleaningTemp} icon={<DeleteOutlined />} style={{ borderRadius: 8 }}>立即清理</Button>
              </Popconfirm>
            </div>
          </div>
          <div className="cat-footer">
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveCleanup} loading={savingCleanup} style={{ background: 'var(--accent-cyan)', borderColor: 'var(--accent-cyan)' }}>保存配置</Button>
          </div>
        </div>
      );

      default: return null;
    }
  };

  if (loading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>;

  return (
    <div style={{ height: 'calc(100vh - 126px)', display: 'flex', gap: 24 }}>
      {/* 左侧分类导航 */}
      <div className="glass-card" style={{ width: 280, flexShrink: 0, padding: 16, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 126px)' }}>
        <div style={{ padding: '8px 12px', marginBottom: 12, flexShrink: 0 }}>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 12 }}>
            系统设置
            {isDirty && <Tag color="warning" style={{ margin: 0, borderRadius: 12, background: 'var(--accent-amber-bg)', color: 'var(--accent-amber)', border: '1px solid var(--accent-amber-border)' }}><SyncOutlined spin /> 未保存</Tag>}
          </h1>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {CATEGORIES.map(cat => (
            <div
              key={cat.key}
              onClick={() => setActiveCategory(cat.key)}
              style={{
                padding: '12px 16px',
                borderRadius: 12,
                marginBottom: 4,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                transition: 'all 0.2s ease',
                background: activeCategory === cat.key ? 'var(' + cat.colorBgVar + ')' : 'transparent',
                border: activeCategory === cat.key ? '1px solid var(' + cat.colorVar + ')' : '1px solid transparent',
              }}
            >
              <div style={{ width: 36, height: 36, borderRadius: 10, background: activeCategory === cat.key ? 'var(' + cat.colorVar + ')' : 'var(--bg-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: activeCategory === cat.key ? '#fff' : 'var(--text-secondary)', fontSize: 16, transition: 'all 0.2s ease' }}>
                {cat.icon}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, color: activeCategory === cat.key ? 'var(' + cat.colorVar + ')' : 'var(--text-primary)', fontSize: 14 }}>{cat.label}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{cat.description}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: '12px 0 0', borderTop: '1px solid var(--glass-border)', marginTop: 12 }}>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveAll} loading={savingAll} block style={{ borderRadius: 12, background: isDirty ? 'linear-gradient(135deg, var(--accent-cyan) 0%, #007bb5 100%)' : 'var(--btn-hover-bg)', borderColor: isDirty ? 'transparent' : 'var(--glass-border)', boxShadow: isDirty ? 'var(--accent-cyan-glow-wide)' : 'none', color: isDirty ? '#fff' : 'var(--text-secondary)' }}>
            保存全局配置
          </Button>
        </div>
      </div>

      {/* 右侧内容区 */}
      <div className="glass-card" style={{ flex: 1, padding: 24, height: 'calc(100vh - 126px)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <Form form={form} layout="vertical" onValuesChange={handleValuesChange} requiredMark={false}>
            {renderContent()}
          </Form>
        </div>
      </div>

    </div>
  );
};

export default Settings;
