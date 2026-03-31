import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Form, Input, Select, Button, message, Spin, Space, InputNumber,
  Table, Tag, Popconfirm, Typography, Row, Col, Tooltip, Progress
} from 'antd';
import {
  SaveOutlined, TranslationOutlined, DownloadOutlined,
  CloudServerOutlined, RocketOutlined,
  InfoCircleOutlined, ReloadOutlined, SyncOutlined,
  LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined
} from '@ant-design/icons';
import { api } from '../services/api';
import type { SystemConfig, ASRModel, ModelDownloadProgress } from '../types/api';

const { Option } = Select;
const { Text } = Typography;

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [savingAll, setSavingAll] = useState(false);
  const [testingEmby, setTestingEmby] = useState(false);
  const [testingTranslation, setTestingTranslation] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  const [models, setModels] = useState<ASRModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelSearch, setModelSearch] = useState('');
  const [modelLangFilter, setModelLangFilter] = useState<string | undefined>(undefined);
  const [downloadProgress, setDownloadProgress] = useState<Record<string, ModelDownloadProgress>>({});
  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  const translationService = Form.useWatch('translation_service', form);
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
  }, [loadModels]);

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
              <Button onClick={testEmby} loading={testingEmby} style={{ borderRadius: 20 }}>
                测试连通性
              </Button>
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

          {/* Translation Pipeline */}
          <div className="glass-card animate-fade-in-up delay-2" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ background: 'var(--accent-emerald-bg)', padding: 8, borderRadius: 8, color: 'var(--accent-emerald)' }}><TranslationOutlined /></div>
                神经翻译管线
              </div>
              <Button onClick={testTranslation} loading={testingTranslation} style={{ borderRadius: 20 }}>
                测试通道
              </Button>
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
              <Button icon={<ReloadOutlined />} onClick={loadModels} loading={modelsLoading} style={{ borderRadius: 20 }} type="text">
                刷新模型列表
              </Button>
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