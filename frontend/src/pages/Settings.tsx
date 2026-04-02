import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Form, Input, Select, Button, message, Spin, Space, InputNumber, Switch, Slider, Collapse,
  Table, Tag, Popconfirm, Typography, Row, Col, Tooltip, Progress
} from 'antd';
import {
  SaveOutlined, TranslationOutlined, DownloadOutlined,
  CloudServerOutlined, RocketOutlined,
  InfoCircleOutlined, ReloadOutlined, SyncOutlined,
  LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined,
  PlusOutlined, DeleteOutlined, SwapOutlined
} from '@ant-design/icons';
import { api } from '../services/api';
import type { SystemConfig, ASRModel, ModelDownloadProgress, LanguageInfo, Library } from '../types/api';

const { Option } = Select;
const { Text } = Typography;

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [savingAll, setSavingAll] = useState(false);
  const [savingEmby, setSavingEmby] = useState(false);
  const [savingTranslation, setSavingTranslation] = useState(false);
  const [savingEngine, setSavingEngine] = useState(false);
  const [savingCleanup, setSavingCleanup] = useState(false);
  const [testingEmby, setTestingEmby] = useState(false);
  const [testingTranslation, setTestingTranslation] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [cleaningTemp, setCleaningTemp] = useState(false);
  const [diskUsage, setDiskUsage] = useState<{ total_mb: number; task_count: number } | null>(null);

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

  const translationService = Form.useWatch('translation_service', form);
  const enableVad = Form.useWatch('enable_vad', form);
  const googleMode = Form.useWatch('google_translate_mode', form);
  const microsoftMode = Form.useWatch('microsoft_translate_mode', form);
  const deeplMode = Form.useWatch('deepl_mode', form);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const config = await api.config.getConfig();
      form.setFieldsValue(config);
      setIsDirty(false);
    } catch (err: any) {
      message.error(err.message || '加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const data = await api.models.listModels();
      setModels(data);
    } catch { } finally {
      setModelsLoading(false);
    }
  }, []);

  const loadVadModels = useCallback(async () => {
    setVadModelsLoading(true);
    try {
      const data = await api.models.listVadModels();
      setVadModels(data);
    } catch { } finally {
      setVadModelsLoading(false);
    }
  }, []);

  const loadLanguages = useCallback(async () => {
    try {
      const data = await api.models.listLanguages();
      setLanguages(data);
    } catch { }
  }, []);

  const loadEmbyLibraries = useCallback(async () => {
    try {
      const data = await api.media.getLibraries();
      setEmbyLibraries(data);
    } catch { }
  }, []);

  const loadDiskUsage = useCallback(async () => {
    try {
      const data = await api.config.getTempDiskUsage();
      setDiskUsage({ total_mb: data.total_mb, task_count: data.task_count });
    } catch { }
  }, []);

  // 清理轮询定时器
  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    };
  }, []);

  const stopPolling = useCallback((modelId: string) => {
    if (pollTimers.current[modelId]) {
      clearInterval(pollTimers.current[modelId]);
      delete pollTimers.current[modelId];
    }
  }, []);

  const startPolling = useCallback((modelId: string) => {
    stopPolling(modelId);
    pollTimers.current[modelId] = setInterval(async () => {
      try {
        const progress = await api.models.getDownloadProgress(modelId);
        setDownloadProgress(prev => ({ ...prev, [modelId]: progress }));
        if (progress.status === 'completed') {
          stopPolling(modelId);
          message.success('模型下载完成');
          loadModels();
          // 3秒后清除进度显示
          setTimeout(() => {
            setDownloadProgress(prev => {
              const next = { ...prev };
              delete next[modelId];
              return next;
            });
          }, 3000);
        } else if (progress.status === 'failed') {
          stopPolling(modelId);
          message.error(progress.error || '模型下载失败');
        }
      } catch {
        stopPolling(modelId);
      }
    }, 1000);
  }, [stopPolling, loadModels]);

  const handleDownload = useCallback(async (modelId: string) => {
    try {
      const progress = await api.models.downloadModel(modelId);
      setDownloadProgress(prev => ({ ...prev, [modelId]: progress }));
      startPolling(modelId);
    } catch (err: any) {
      message.error(err.message || '启动下载失败');
    }
  }, [startPolling]);

  const handleVadDownload = useCallback(async (modelId: string) => {
    try {
      const progress = await api.models.downloadVadModel(modelId);
      setDownloadProgress(prev => ({ ...prev, [modelId]: progress }));
      // 复用 ASR 的轮询逻辑（进度端点相同）
      stopPolling(modelId);
      pollTimers.current[modelId] = setInterval(async () => {
        try {
          const p = await api.models.getDownloadProgress(modelId);
          setDownloadProgress(prev => ({ ...prev, [modelId]: p }));
          if (p.status === 'completed') {
            stopPolling(modelId);
            message.success('VAD 模型下载完成');
            loadVadModels();
            setTimeout(() => {
              setDownloadProgress(prev => { const next = { ...prev }; delete next[modelId]; return next; });
            }, 3000);
          } else if (p.status === 'failed') {
            stopPolling(modelId);
            message.error(p.error || 'VAD 模型下载失败');
          }
        } catch { stopPolling(modelId); }
      }, 1000);
    } catch (err: any) {
      message.error(err.message || 'VAD 模型下载失败');
    }
  }, [stopPolling, loadVadModels]);

  // 过滤模型列表
  const filteredModels = React.useMemo(() => {
    let list = models;
    
    // 搜索过滤
    if (modelSearch) {
      const kw = modelSearch.toLowerCase();
      list = list.filter(m => 
        m.id.toLowerCase().includes(kw) || 
        m.name.toLowerCase().includes(kw)
      );
    }
    
    // 语言过滤
    if (modelLangFilter) {
      list = list.filter(m => m.languages.includes(modelLangFilter));
    }
    
    return list;
  }, [models, modelSearch, modelLangFilter]);

  // 从模型列表中提取所有可用语言
  const availableLanguages = React.useMemo(() => {
    const langSet = new Set<string>();
    models.forEach(m => m.languages.forEach(l => langSet.add(l)));
    return Array.from(langSet).sort();
  }, [models]);

  useEffect(() => {
    loadConfig();
    loadModels();
    loadVadModels();
    loadLanguages();
    loadEmbyLibraries();
    loadDiskUsage();
  }, [loadModels, loadVadModels, loadLanguages, loadEmbyLibraries, loadDiskUsage]);

  const handleValuesChange = () => {
    setIsDirty(true);
  };

  const handleSaveAll = async () => {
    try {
      const values = await form.validateFields();
      setSavingAll(true);
      await api.config.updateConfig(values as SystemConfig);
      message.success('核心配置库同步完成');
      setIsDirty(false);
    } catch (err: any) {
      message.error(err.message || '参数校验未通过');
    } finally { setSavingAll(false); }
  };

  // 分区保存函数
  const handleSaveEmby = async () => {
    try {
      const values = {
        emby_url: form.getFieldValue('emby_url'),
        emby_api_key: form.getFieldValue('emby_api_key'),
      };
      setSavingEmby(true);
      await api.config.partialUpdateConfig(values);
      message.success('Emby 配置已保存');
    } catch (err: any) {
      message.error(err.message || '保存失败');
    } finally { setSavingEmby(false); }
  };

  const handleSaveTranslation = async () => {
    try {
      const service = form.getFieldValue('translation_service');
      const values: any = { translation_service: service };
      
      if (service === 'openai') {
        values.openai_api_key = form.getFieldValue('openai_api_key');
        values.openai_model = form.getFieldValue('openai_model');
      } else if (service === 'deepseek') {
        values.deepseek_api_key = form.getFieldValue('deepseek_api_key');
      } else if (service === 'local') {
        values.local_llm_url = form.getFieldValue('local_llm_url');
      } else if (service === 'google') {
        values.google_translate_mode = form.getFieldValue('google_translate_mode');
        values.google_api_key = form.getFieldValue('google_api_key');
      } else if (service === 'microsoft') {
        values.microsoft_translate_mode = form.getFieldValue('microsoft_translate_mode');
        values.microsoft_api_key = form.getFieldValue('microsoft_api_key');
        values.microsoft_region = form.getFieldValue('microsoft_region');
      } else if (service === 'baidu') {
        values.baidu_app_id = form.getFieldValue('baidu_app_id');
        values.baidu_secret_key = form.getFieldValue('baidu_secret_key');
      } else if (service === 'deepl') {
        values.deepl_mode = form.getFieldValue('deepl_mode');
        values.deepl_api_key = form.getFieldValue('deepl_api_key');
        values.deeplx_url = form.getFieldValue('deeplx_url');
      }
      
      setSavingTranslation(true);
      await api.config.partialUpdateConfig(values);
      message.success('翻译配置已保存');
    } catch (err: any) {
      message.error(err.message || '保存失败');
    } finally { setSavingTranslation(false); }
  };

  const handleSaveEngine = async () => {
    try {
      const values = {
        asr_engine: form.getFieldValue('asr_engine'),
        asr_model_id: form.getFieldValue('asr_model_id'),
        source_language: form.getFieldValue('source_language'),
        target_language: form.getFieldValue('target_language'),
        enable_vad: form.getFieldValue('enable_vad'),
        vad_model_id: form.getFieldValue('vad_model_id'),
        vad_threshold: form.getFieldValue('vad_threshold'),
        vad_min_silence_duration: form.getFieldValue('vad_min_silence_duration'),
        vad_min_speech_duration: form.getFieldValue('vad_min_speech_duration'),
        vad_max_speech_duration: form.getFieldValue('vad_max_speech_duration'),
        max_concurrent_tasks: form.getFieldValue('max_concurrent_tasks'),
        cloud_asr_url: form.getFieldValue('cloud_asr_url'),
        cloud_asr_api_key: form.getFieldValue('cloud_asr_api_key'),
      };
      setSavingEngine(true);
      await api.config.partialUpdateConfig(values);
      message.success('引擎配置已保存');
    } catch (err: any) {
      message.error(err.message || '保存失败');
    } finally { setSavingEngine(false); }
  };

  const handleSaveCleanup = async () => {
    try {
      const values = {
        cleanup_temp_files_on_success: form.getFieldValue('cleanup_temp_files_on_success'),
      };
      setSavingCleanup(true);
      await api.config.partialUpdateConfig(values);
      message.success('清理配置已保存');
    } catch (err: any) {
      message.error(err.message || '保存失败');
    } finally { setSavingCleanup(false); }
  };

  const handleCleanupTemp = async () => {
    setCleaningTemp(true);
    try {
      const result = await api.config.cleanupTemp();
      message.success(result.message);
      loadDiskUsage();
    } catch (err: any) {
      message.error(err.message || '清理失败');
    } finally { setCleaningTemp(false); }
  };

  const testEmby = async () => {
    setTestingEmby(true);
    try {
      await api.config.testEmby({
        emby_url: form.getFieldValue('emby_url'),
        emby_api_key: form.getFieldValue('emby_api_key')
      });
      message.success('Emby 节点连接成功');
    } catch (err: any) {
      message.error(err.message || 'Emby 连接失败');
    } finally { setTestingEmby(false); }
  };

  const testTranslation = async () => {
    setTestingTranslation(true);
    try {
      const service = form.getFieldValue('translation_service');
      const payload: any = { translation_service: service };
      
      if (service === 'openai') {
        payload.api_key = form.getFieldValue('openai_api_key');
        payload.model = form.getFieldValue('openai_model');
      } else if (service === 'deepseek') {
        payload.api_key = form.getFieldValue('deepseek_api_key');
      } else if (service === 'local') {
        payload.api_url = form.getFieldValue('local_llm_url');
      } else if (service === 'google') {
        payload.google_translate_mode = form.getFieldValue('google_translate_mode');
        payload.api_key = form.getFieldValue('google_api_key');
      } else if (service === 'microsoft') {
        payload.microsoft_translate_mode = form.getFieldValue('microsoft_translate_mode');
        payload.api_key = form.getFieldValue('microsoft_api_key');
        payload.microsoft_region = form.getFieldValue('microsoft_region');
      } else if (service === 'baidu') {
        payload.baidu_app_id = form.getFieldValue('baidu_app_id');
        payload.baidu_secret_key = form.getFieldValue('baidu_secret_key');
      } else if (service === 'deepl') {
        payload.deepl_mode = form.getFieldValue('deepl_mode');
        payload.api_key = form.getFieldValue('deepl_api_key');
        payload.deeplx_url = form.getFieldValue('deeplx_url');
      }
      
      await api.config.testTranslation(payload);
      message.success('翻译 API 通道畅通');
    } catch (err: any) {
      message.error(err.message || '翻译通道连接失败');
    } finally { setTestingTranslation(false); }
  };

  const columns = [
    {
      title: '神经模型标识',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: ASRModel) => (
        <Space>
          <Text strong style={{ color: 'var(--text-primary)' }}>{text}</Text>
          {record.active && <Tag color="success" style={{ background: 'var(--accent-emerald-bg)', border: '1px solid var(--accent-emerald)', color: 'var(--accent-emerald)' }}>当前激活</Tag>}
          {record.installed && !record.active && <Tag color="processing" style={{ background: 'var(--accent-cyan-bg)', border: '1px solid var(--accent-cyan)', color: 'var(--accent-cyan)' }}>就绪</Tag>}
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => (
        <Tag color={type === 'online' ? 'blue' : 'green'} style={{ background: type === 'online' ? 'var(--accent-cyan-bg)' : 'var(--accent-emerald-bg)', border: 'none' }}>
          {type === 'online' ? '流式' : '离线'}
        </Tag>
      )
    },
    {
      title: '语言支持',
      dataIndex: 'languages',
      key: 'languages',
      render: (langs: string[]) => (langs || []).slice(0, 3).map(lang => <Tag key={lang} style={{ background: 'var(--bg-tag)', border: 'none', fontSize: 10 }}>{lang}</Tag>)
    },
    {
      title: '参数量',
      dataIndex: 'size',
      key: 'size',
      width: 100,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: ASRModel) => {
        if (record.installed) {
          return (
            <Space size="middle">
              {!record.active && (
                <Button type="link" onClick={() => api.models.activateModel(record.id).then(loadModels)} style={{ padding: 0, color: 'var(--accent-cyan)' }}>激活</Button>
              )}
              <Popconfirm title="确认删除神经模型?" onConfirm={() => api.models.deleteModel(record.id).then(loadModels)}>
                <Button type="link" danger style={{ padding: 0 }}>卸载</Button>
              </Popconfirm>
            </Space>
          );
        }
        const progress = downloadProgress[record.id];
        if (progress && (progress.status === 'downloading' || progress.status === 'extracting')) {
          return (
            <div style={{ minWidth: 120 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                <LoadingOutlined spin style={{ fontSize: 12, color: 'var(--accent-cyan)' }} />
                <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {progress.status === 'extracting' ? '解压中...' : `${progress.progress}%`}
                </Text>
              </div>
              <Progress
                percent={progress.progress}
                size="small"
                showInfo={false}
                strokeColor="var(--accent-cyan)"
                trailColor="var(--glass-border)"
              />
            </div>
          );
        }
        if (progress?.status === 'completed') {
          return (
            <Space>
              <CheckCircleOutlined style={{ color: 'var(--accent-emerald)' }} />
              <Text style={{ color: 'var(--accent-emerald)', fontSize: 12 }}>下载完成</Text>
            </Space>
          );
        }
        if (progress?.status === 'failed') {
          return (
            <Space>
              <Tooltip title={progress.error}>
                <Button type="link" danger icon={<CloseCircleOutlined />} onClick={() => handleDownload(record.id)} style={{ padding: 0 }}>
                  失败，重试
                </Button>
              </Tooltip>
            </Space>
          );
        }
        return (
          <Button type="link" icon={<DownloadOutlined />} onClick={() => handleDownload(record.id)} style={{ padding: 0, color: 'var(--accent-emerald)' }}>
            下载权重
          </Button>
        );
      },
    },
  ];

  if (loading) return <div style={{ padding: 100, textAlign: 'center' }}><Spin size="large" /></div>;

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', paddingBottom: 60 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 12 }}>
            系统核心配置
            {isDirty && <Tag color="warning" style={{ margin: 0, borderRadius: 12, background: 'var(--accent-amber-bg)', color: 'var(--accent-amber)', border: '1px solid var(--accent-amber-border)' }}><SyncOutlined spin /> 未保存更改</Tag>}
          </h1>
          <Text type="secondary" style={{ fontSize: 13 }}>调整服务参数与神经引擎设置，更改将在保存后生效</Text>
        </div>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSaveAll}
          loading={savingAll}
          style={{
            height: 40,
            padding: '0 24px',
            borderRadius: 20,
            background: isDirty ? 'linear-gradient(135deg, var(--accent-cyan) 0%, #007bb5 100%)' : 'var(--btn-hover-bg)',
            borderColor: isDirty ? 'transparent' : 'var(--glass-border)',
            boxShadow: isDirty ? 'var(--accent-cyan-glow-wide)' : 'none',
            color: isDirty ? '#fff' : 'var(--text-secondary)',
            transition: 'all 0.4s var(--ease-spring)',
            transform: isDirty ? 'scale(1.05)' : 'scale(1)',
          }}
        >
          保存全局配置
        </Button>
      </div>

      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleValuesChange}
        requiredMark={false}
      >
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          
          {/* Emby Node Config */}
          <div className="glass-card animate-fade-in-up delay-1" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ background: 'var(--accent-cyan-bg)', padding: 8, borderRadius: 8, color: 'var(--accent-cyan)' }}><CloudServerOutlined /></div>
                Emby 核心节点
              </div>
              <Space>
                <Button onClick={testEmby} loading={testingEmby} style={{ borderRadius: 20 }}>
                  测试连通性
                </Button>
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveEmby} loading={savingEmby} style={{ borderRadius: 20, background: 'var(--accent-cyan)' }}>
                  保存
                </Button>
              </Space>
            </div>
            
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="emby_url" label="服务器网络地址" rules={[{ required: true }]}>
                  <Input placeholder="http://localhost:8096" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="emby_api_key" label={
                  <Space>API 通行密钥 <Tooltip title="从 Emby 后台生成"><InfoCircleOutlined /></Tooltip></Space>
                } rules={[{ required: true }]}>
                  <Input.Password placeholder="输入您的 API Key" />
                </Form.Item>
              </Col>
            </Row>
          </div>

          {/* Path Mapping */}
          <div className="glass-card animate-fade-in-up delay-2" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ background: 'var(--accent-amber-bg)', padding: 8, borderRadius: 8, color: 'var(--accent-amber)' }}><SwapOutlined /></div>
                路径映射
              </div>
              <Tooltip title="将 Emby 服务器上的视频路径映射为本地可访问路径，用于字幕文件回写">
                <InfoCircleOutlined style={{ color: 'var(--text-secondary)' }} />
              </Tooltip>
            </div>

            <div style={{ marginBottom: 16, padding: 12, background: 'var(--info-bg)', borderRadius: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
              配置 Emby 视频路径到本地挂载路径的映射规则。字幕生成完成后，系统会将 SRT 文件复制到视频同目录下，然后刷新 Emby 元数据使字幕生效。
              <br />
              <span style={{ marginTop: 6, display: 'block' }}>
                💡 支持跨平台路径：Emby（Linux）路径如 <code>/mnt/media</code>，本地（Windows）挂载路径如 <code>Z:\Media</code> 或 <code>Z:/Media</code>，系统会自动转换分隔符。
              </span>
            </div>

            <Form.List name="path_mappings">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <div
                      key={key}
                      style={{
                        background: 'var(--bg-input)',
                        padding: 16,
                        borderRadius: 'var(--radius-inner)',
                        border: '1px solid var(--glass-border)',
                        marginBottom: 12,
                      }}
                    >
                      <Row gutter={12} align="top">
                        <Col span={5}>
                          <Form.Item
                            {...restField}
                            name={[name, 'name']}
                            rules={[{ required: true, message: '请输入名称' }]}
                            style={{ marginBottom: 0 }}
                          >
                            <Input placeholder="规则名称" size="small" />
                          </Form.Item>
                        </Col>
                        <Col span={7}>
                          <Form.Item
                            {...restField}
                            name={[name, 'emby_prefix']}
                            rules={[{ required: true, message: '请输入 Emby 路径前缀' }]}
                            style={{ marginBottom: 0 }}
                          >
                            <Input placeholder="Emby 路径前缀，如 /mnt/media" size="small" />
                          </Form.Item>
                        </Col>
                        <Col span={7}>
                          <Form.Item
                            {...restField}
                            name={[name, 'local_prefix']}
                            rules={[{ required: true, message: '请输入本地路径前缀' }]}
                            style={{ marginBottom: 0 }}
                          >
                            <Input placeholder="本地路径前缀，如 Z:\Media 或 /mnt/drive" size="small" />
                          </Form.Item>
                        </Col>
                        <Col span={4}>
                          <Form.Item
                            {...restField}
                            name={[name, 'library_ids']}
                            initialValue={[]}
                            style={{ marginBottom: 0 }}
                          >
                            <Select
                              mode="multiple"
                              placeholder="关联媒体库"
                              size="small"
                              maxTagCount={1}
                              allowClear
                            >
                              {embyLibraries.map((lib) => (
                                <Option key={lib.id} value={lib.id}>{lib.name}</Option>
                              ))}
                            </Select>
                          </Form.Item>
                        </Col>
                        <Col span={1} style={{ display: 'flex', justifyContent: 'center', paddingTop: 4 }}>
                          <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            size="small"
                            onClick={() => remove(name)}
                          />
                        </Col>
                      </Row>
                    </div>
                  ))}
                  <Button
                    type="dashed"
                    onClick={() => add({ name: '', emby_prefix: '', local_prefix: '', library_ids: [] })}
                    block
                    icon={<PlusOutlined />}
                    style={{ borderColor: 'var(--glass-border)' }}
                  >
                    添加映射规则
                  </Button>
                </>
              )}
            </Form.List>
          </div>

          {/* Translation Pipeline */}
          <div className="glass-card animate-fade-in-up delay-3" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ background: 'var(--accent-emerald-bg)', padding: 8, borderRadius: 8, color: 'var(--accent-emerald)' }}><TranslationOutlined /></div>
                翻译服务
              </div>
              <Space>
                <Button onClick={testTranslation} loading={testingTranslation} style={{ borderRadius: 20 }}>
                  测试通道
                </Button>
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveTranslation} loading={savingTranslation} style={{ borderRadius: 20, background: 'var(--accent-emerald)' }}>
                  保存
                </Button>
              </Space>
            </div>
            
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
            
            <div style={{
              background: 'var(--bg-input)',
              padding: 16,
              borderRadius: 'var(--radius-inner)',
              border: '1px solid var(--glass-border)'
            }}>
              {translationService === 'openai' && (
                <Row gutter={24}>
                  <Col span={12}>
                    <Form.Item name="openai_api_key" label="OpenAI API Key" rules={[{ required: true }]}>
                      <Input.Password placeholder="sk-..." />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="openai_model" label="大语言模型" initialValue="gpt-4">
                      <Input placeholder="gpt-4o / gpt-3.5-turbo" />
                    </Form.Item>
                  </Col>
                </Row>
              )}
              {translationService === 'deepseek' && (
                <Form.Item name="deepseek_api_key" label="DeepSeek API Key" rules={[{ required: true }]}>
                  <Input.Password placeholder="sk-..." />
                </Form.Item>
              )}
              {translationService === 'local' && (
                <Form.Item name="local_llm_url" label="本地模型 Endpoint" rules={[{ required: true }]}>
                  <Input placeholder="http://localhost:11434" />
                </Form.Item>
              )}
              {translationService === 'google' && (
                <Row gutter={24}>
                  <Col span={12}>
                    <Form.Item name="google_translate_mode" label="使用模式" initialValue="free">
                      <Select>
                        <Option value="free">免费版</Option>
                        <Option value="api">官方 API</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="google_api_key" label="API Key (API模式)" rules={[{ required: googleMode === 'api' }]}>
                      <Input.Password placeholder="仅 API 模式需要" />
                    </Form.Item>
                  </Col>
                </Row>
              )}
              {translationService === 'microsoft' && (
                <Row gutter={24}>
                  <Col span={8}>
                    <Form.Item name="microsoft_translate_mode" label="使用模式" initialValue="free">
                      <Select>
                        <Option value="free">免费版</Option>
                        <Option value="api">官方 API</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="microsoft_api_key" label="API Key" rules={[{ required: microsoftMode === 'api' }]}>
                      <Input.Password placeholder="仅 API 模式需要" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="microsoft_region" label="区域" initialValue="global">
                      <Input placeholder="global / eastasia" />
                    </Form.Item>
                  </Col>
                </Row>
              )}
              {translationService === 'baidu' && (
                <Row gutter={24}>
                  <Col span={12}>
                    <Form.Item name="baidu_app_id" label="百度 APP ID" rules={[{ required: true }]}>
                      <Input placeholder="从百度翻译开放平台获取" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="baidu_secret_key" label="Secret Key" rules={[{ required: true }]}>
                      <Input.Password placeholder="密钥" />
                    </Form.Item>
                  </Col>
                </Row>
              )}
              {translationService === 'deepl' && (
                <Row gutter={24}>
                  <Col span={8}>
                    <Form.Item name="deepl_mode" label="使用模式" initialValue="deeplx">
                      <Select>
                        <Option value="deeplx">DeepLX (免费)</Option>
                        <Option value="api">官方 API</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="deepl_api_key" label="API Key" rules={[{ required: deeplMode === 'api' }]}>
                      <Input.Password placeholder="仅 API 模式需要" />
                    </Form.Item>
                  </Col>
                  <Col span={8}>
                    <Form.Item name="deeplx_url" label="DeepLX 地址" rules={[{ required: deeplMode === 'deeplx' }]}>
                      <Input placeholder="http://localhost:1188" />
                    </Form.Item>
                  </Col>
                </Row>
              )}
            </div>
          </div>

          {/* AI Engine Settings */}
          <div className="glass-card animate-fade-in-up delay-3" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ background: 'var(--accent-amber-bg)', padding: 8, borderRadius: 8, color: 'var(--accent-amber)' }}><RocketOutlined /></div>
                ASR 识别引擎配置
              </div>
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => { loadModels(); loadVadModels(); }} loading={modelsLoading} style={{ borderRadius: 20 }} type="text">
                  刷新模型列表
                </Button>
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveEngine} loading={savingEngine} style={{ borderRadius: 20, background: 'var(--accent-amber)' }}>
                  保存
                </Button>
              </Space>
            </div>
            
            <Row gutter={24} style={{ marginBottom: 24 }}>
              <Col span={24}>
                <Form.Item name="asr_engine" label="默认推理引擎">
                  <Select dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                    <Option value="sherpa-onnx">本地模型 (Sherpa ONNX)</Option>
                    <Option value="cloud">云端 API</Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>

            {/* 本地模型配置区 */}
            <div style={{ 
              background: 'var(--accent-emerald-bg)',
              padding: 16,
              borderRadius: 'var(--radius-inner)',
              border: '1px solid var(--accent-emerald-border)',
              marginBottom: 24
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, color: 'var(--accent-emerald)', fontWeight: 500 }}>
                <RocketOutlined />
                本地模型配置
              </div>
              <Row gutter={24}>
                <Col span={16}>
                  <Form.Item name="asr_model_id" label="已激活模型">
                    <Select
                      placeholder="请先下载并激活模型"
                      disabled
                      dropdownStyle={{ background: 'var(--bg-elevated)' }}
                    >
                      {models.filter(m => m.installed).map(m => (
                        <Option key={m.id} value={m.id}>
                          {m.name} {m.active && <Tag color="success" style={{ marginLeft: 8 }}>当前激活</Tag>}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    在下方模型列表中下载并激活模型后自动应用
                  </Text>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_concurrent_tasks" label="并行处理线程数">
                    <InputNumber min={1} max={16} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              {/* 语言配置 */}
              <Row gutter={24} style={{ marginTop: 16 }}>
                <Col span={12}>
                  <Form.Item name="source_language" label="源语言（音频语言）">
                    <Select placeholder="选择源语言" dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                      {languages.map(lang => (
                        <Option key={lang.code} value={lang.code}>{lang.name} ({lang.code})</Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="target_language" label="目标语言（字幕语言）">
                    <Select placeholder="选择目标语言" dropdownStyle={{ background: 'var(--bg-elevated)' }}>
                      {languages.map(lang => (
                        <Option key={lang.code} value={lang.code}>{lang.name} ({lang.code})</Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 12 }}>
                源语言与目标语言相同时将跳过翻译步骤，仅生成转录字幕
              </Text>

              {/* VAD 配置 */}
              <div style={{ marginTop: 16, padding: 12, borderRadius: 8, background: 'var(--bg-subtle)', border: '1px solid var(--glass-border)' }}>
                <Row align="middle" gutter={16}>
                  <Col flex="auto">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 500, color: 'var(--text-primary)' }}>
                      <InfoCircleOutlined style={{ color: 'var(--accent-amber)' }} />
                      语音活动检测 (VAD)
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      启用后使用 Silero VAD 检测语音段，获得更精确的字幕时间戳（仅离线模型有效）
                    </Text>
                  </Col>
                  <Col>
                    <Form.Item name="enable_vad" valuePropName="checked" style={{ margin: 0 }}>
                      <Switch />
                    </Form.Item>
                  </Col>
                </Row>

                {enableVad && (
                  <div style={{ marginTop: 12 }}>
                    <Row gutter={24}>
                      <Col span={16}>
                        <Form.Item name="vad_model_id" label="VAD 模型">
                          <Select
                            placeholder={vadModels.filter(m => m.installed).length ? '选择 VAD 模型' : '请先下载 VAD 模型'}
                            dropdownStyle={{ background: 'var(--bg-elevated)' }}
                            loading={vadModelsLoading}
                            disabled={!vadModels.some(m => m.installed)}
                          >
                            {vadModels.filter(m => m.installed).map(m => (
                              <Option key={m.id} value={m.id}>
                                {m.name} {m.active && <Tag color="success" style={{ marginLeft: 8 }}>激活</Tag>}
                              </Option>
                            ))}
                          </Select>
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label=" ">
                          <Button onClick={loadVadModels} loading={vadModelsLoading} icon={<ReloadOutlined />} type="text" size="small">
                            刷新
                          </Button>
                        </Form.Item>
                      </Col>
                    </Row>

                    {/* VAD 模型下载列表 */}
                          {vadModelsLoading ? (
                            <div style={{ textAlign: 'center', padding: 16 }}>
                              <LoadingOutlined spin style={{ fontSize: 20, color: 'var(--accent-cyan)' }} />
                              <div style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 12 }}>加载中...</div>
                            </div>
                          ) : vadModels.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: 16 }}>
                              <Text type='secondary' style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                                暂无 VAD 模型，点击刷新按钮加载
                              </Text>
                              <Button size='small' icon={<ReloadOutlined />} onClick={() => { api.models.refreshModels().then(loadModels); loadVadModels(); }} loading={vadModelsLoading}>
                                加载 VAD 模型
                              </Button>
                            </div>
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
                                  <Space size={4}>
                                    <LoadingOutlined spin style={{ fontSize: 12, color: 'var(--accent-cyan)' }} />
                                    <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{progress.progress}%</Text>
                                  </Space>
                                ) : m.installed ? (
                                  <Button type="link" size="small" onClick={() => api.models.activateVadModel(m.id).then(() => { loadVadModels(); loadConfig(); })} style={{ padding: 0, color: 'var(--accent-cyan)' }}>
                                    {m.active ? '已激活' : '激活'}
                                  </Button>
                                ) : (
                                  <Button type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleVadDownload(m.id)} style={{ padding: 0, color: 'var(--accent-emerald)' }}>
                                    下载
                                  </Button>
                                )}
                              </Space>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* VAD 高级参数 */}
                    <Collapse ghost size="small" items={[{
                      key: 'vad-advanced',
                      label: <Text type="secondary" style={{ fontSize: 12 }}>VAD 高级参数</Text>,
                      children: (
                        <>
                          <Row gutter={24}>
                            <Col span={12}>
                              <Form.Item name="vad_threshold" label="语音检测阈值">
                                <Slider min={0.1} max={0.9} step={0.05} marks={{ 0.2: '0.2', 0.5: '0.5', 0.8: '0.8' }} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="vad_max_speech_duration" label="最大语音段长度 (秒)">
                                <InputNumber min={1} max={60} step={1} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={24}>
                            <Col span={12}>
                              <Form.Item name="vad_min_silence_duration" label="最小静音时长 (秒)">
                                <InputNumber min={0.1} max={5} step={0.1} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="vad_min_speech_duration" label="最小语音时长 (秒)">
                                <InputNumber min={0.05} max={5} step={0.05} style={{ width: '100%' }} />
                              </Form.Item>
                            </Col>
                          </Row>
                        </>
                      ),
                    }]} />
                  </div>
                )}
              </div>
            </div>

            {/* 云端 API 配置区 */}
            <div style={{ 
              background: 'var(--accent-cyan-bg)',
              padding: 16,
              borderRadius: 'var(--radius-inner)',
              border: '1px solid var(--accent-cyan-border)',
              marginBottom: 24
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, color: 'var(--accent-cyan)', fontWeight: 500 }}>
                <CloudServerOutlined />
                云端 API 配置
              </div>
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item name="cloud_asr_url" label="API 服务地址">
                    <Input placeholder="https://api.example.com/asr" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="cloud_asr_api_key" label="API 密钥">
                    <Input.Password placeholder="输入云端 API Key" />
                  </Form.Item>
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 12 }}>
                配置云端 API 后，可在创建任务时选择使用云端识别（速度更快，需要网络）
              </Text>
            </div>

            <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--glass-border)', background: 'var(--bg-subtle)' }}>
              <Row gutter={12}>
                <Col flex="auto">
                  <Input 
                    placeholder="搜索模型名称..." 
                    allowClear 
                    value={modelSearch} 
                    onChange={e => setModelSearch(e.target.value)}
                  />
                </Col>
                <Col flex="180px">
                  <Select 
                    placeholder="按语言筛选" 
                    allowClear 
                    value={modelLangFilter} 
                    onChange={v => setModelLangFilter(v)}
                    style={{ width: '100%' }}
                    dropdownStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--glass-border)' }}
                  >
                    {availableLanguages.map(lang => (
                      <Option key={lang} value={lang}>{lang}</Option>
                    ))}
                  </Select>
                </Col>
              </Row>
            </div>

            <Table
              columns={columns}
              dataSource={filteredModels}
              rowKey="id"
              pagination={{
                pageSize: 10,
                showSizeChanger: false,
                showTotal: (total) => `共 ${total} 个模型`,
                style: { marginRight: 16 }
              }}
              loading={modelsLoading}
              className="custom-table"
              style={{ background: 'transparent' }}
            />
          </div>

          {/* 临时文件清理 */}
          <div className="glass-card animate-fade-in-up delay-4" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ background: 'rgba(239,68,68,0.12)', padding: 8, borderRadius: 8, color: '#ef4444' }}>🗑️</div>
                临时文件管理
              </div>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSaveCleanup}
                loading={savingCleanup}
                style={{ borderRadius: 20, background: 'var(--accent-cyan)' }}
              >
                保存
              </Button>
            </div>

            <div style={{ marginBottom: 20, padding: 14, background: 'var(--bg-input)', borderRadius: 8, border: '1px solid var(--glass-border)' }}>
              <Row align="middle" gutter={16}>
                <Col flex="auto">
                  <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
                    任务成功后自动清理临时文件
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    开启后，字幕生成成功时自动删除音频提取、ASR 中间结果等临时文件。
                    关闭则保留所有中间产物，方便调试排查问题。
                  </Text>
                </Col>
                <Col>
                  <Form.Item name="cleanup_temp_files_on_success" valuePropName="checked" style={{ margin: 0 }}>
                    <Switch />
                  </Form.Item>
                </Col>
              </Row>
            </div>

            <div style={{ padding: 14, background: 'var(--bg-input)', borderRadius: 8, border: '1px solid var(--glass-border)' }}>
              <Row align="middle" justify="space-between" style={{ marginBottom: 12 }}>
                <Col>
                  <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
                    手动清理所有临时文件
                  </div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    立即删除 data/tasks/ 下所有任务目录（包括失败任务的中间产物）
                  </Text>
                </Col>
                <Col>
                  <Space>
                    {diskUsage !== null && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        当前占用：<span style={{ color: diskUsage.total_mb > 500 ? '#ef4444' : 'var(--accent-cyan)', fontWeight: 600 }}>
                          {diskUsage.total_mb} MB
                        </span>
                        &nbsp;({diskUsage.task_count} 个任务目录)
                      </Text>
                    )}
                    <Button
                      icon={<ReloadOutlined />}
                      size="small"
                      type="text"
                      onClick={loadDiskUsage}
                      style={{ color: 'var(--text-secondary)' }}
                    />
                  </Space>
                </Col>
              </Row>
              <Popconfirm
                title="确认清理所有临时文件？"
                description="此操作不可撤销，将删除所有任务的中间产物（音频、ASR 结果等）"
                onConfirm={handleCleanupTemp}
                okText="确认清理"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button
                  danger
                  loading={cleaningTemp}
                  icon={<DeleteOutlined />}
                  style={{ borderRadius: 8 }}
                >
                  立即清理
                </Button>
              </Popconfirm>
            </div>
          </div>

        </Space>
      </Form>
      
      <style>{`
        .custom-table .ant-table {
          background: transparent !important;
        }
        .custom-table .ant-table-thead > tr > th {
          background: var(--table-header-bg) !important;
          border-bottom: 1px solid var(--glass-border) !important;
          color: var(--text-secondary) !important;
          font-size: 12px;
        }
        .custom-table .ant-table-tbody > tr > td {
          border-bottom: 1px solid var(--glass-border) !important;
        }
        .custom-table .ant-table-tbody > tr:hover > td {
          background: var(--table-row-hover) !important;
        }
        .ant-form-item-label > label {
          color: var(--text-secondary) !important;
          font-size: 13px !important;
        }

        /* Fix input focus double border */
        .ant-input:hover {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input:focus,
        .ant-input-focused {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
          outline: none !important;
        }

        /* Fix Input with allowClear (affix wrapper) double border */
        .ant-input-affix-wrapper {
          padding: 0 !important;
          border: none !important;
          background: transparent !important;
        }

        .ant-input-affix-wrapper:hover,
        .ant-input-affix-wrapper:focus,
        .ant-input-affix-wrapper-focused {
          border: none !important;
          box-shadow: none !important;
        }

        .ant-input-affix-wrapper .ant-input {
          border: 1px solid var(--glass-border) !important;
          background: var(--bg-input) !important;
        }

        .ant-input-affix-wrapper:hover .ant-input {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input-affix-wrapper-focused .ant-input,
        .ant-input-affix-wrapper .ant-input:focus {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
        }

        /* Fix Password Input double border */
        .ant-input-password {
          padding: 0 !important;
          border: none !important;
          background: transparent !important;
        }

        .ant-input-password:hover,
        .ant-input-password:focus,
        .ant-input-password-focused {
          border: none !important;
          box-shadow: none !important;
        }

        .ant-input-password .ant-input {
          border: 1px solid var(--glass-border) !important;
          background: var(--bg-input) !important;
        }

        .ant-input-password:hover .ant-input {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input-password-focused .ant-input,
        .ant-input-password .ant-input:focus {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
        }

        .ant-select:not(.ant-select-disabled):hover .ant-select-selector {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-select-focused .ant-select-selector {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
          outline: none !important;
        }

        .ant-input-number:hover {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input-number-focused {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
          outline: none !important;
        }
      `}</style>
    </div>
  );
};

export default Settings;
