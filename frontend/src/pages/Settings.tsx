import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  message,
  Spin,
  Alert,
  Space,
  InputNumber,
  Table,
  Tag,
  Progress,
  Popconfirm,
  Collapse,
} from 'antd';
import {
  SaveOutlined,
  ApiOutlined,
  TranslationOutlined,
  CheckCircleOutlined,
  DownloadOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { SystemConfig, ASRModel, ModelDownloadProgress, LanguageInfo } from '../types/api';

const { Option } = Select;

// ── 语言标签映射 ──────────────────────────────────────────────────────────

const LANG_LABELS: Record<string, string> = {
  zh: '中文', en: 'English', ja: '日本語', ko: '한국어',
  fr: 'Français', de: 'Deutsch', es: 'Español', ru: 'Русский',
  pt: 'Português', it: 'Italiano', th: 'ไทย', vi: 'Tiếng Việt',
  ar: 'العربية', yue: '粤语',
};

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [savingEmby, setSavingEmby] = useState(false);
  const [savingTranslation, setSavingTranslation] = useState(false);
  const [savingAll, setSavingAll] = useState(false);
  const [testingEmby, setTestingEmby] = useState(false);
  const [testingTranslation, setTestingTranslation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 模型管理状态
  const [models, setModels] = useState<ASRModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [downloadingModels, setDownloadingModels] = useState<Record<string, ModelDownloadProgress>>({});
  const pollTimerRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);

  // 监听表单字段变化
  const asrEngine = Form.useWatch('asr_engine', form);
  const translationService = Form.useWatch('translation_service', form);

  // ── 加载 ──

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const config = await api.config.getConfig();
      form.setFieldsValue(config);
    } catch (err: any) {
      setError(err.message || '加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const data = await api.models.listModels();
      setModels(data);
    } catch {
      // 静默失败
    } finally {
      setModelsLoading(false);
    }
  }, []);

  const loadLanguages = useCallback(async () => {
    try {
      const data = await api.models.listLanguages();
      setLanguages(data);
    } catch {
      // 静默失败，使用内置映射
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadModels();
    loadLanguages();
    return () => {
      // 清理轮询
      Object.values(pollTimerRef.current).forEach(clearInterval);
    };
  }, [loadModels, loadLanguages]);

  // ── 模型操作 ──

  const handleDownload = async (modelId: string) => {
    try {
      const progress = await api.models.downloadModel(modelId);
      setDownloadingModels(prev => ({ ...prev, [modelId]: progress }));

      // 开始轮询进度
      const timer = setInterval(async () => {
        try {
          const p = await api.models.getDownloadProgress(modelId);
          setDownloadingModels(prev => ({ ...prev, [modelId]: p }));

          if (p.status === 'completed' || p.status === 'failed') {
            clearInterval(timer);
            delete pollTimerRef.current[modelId];
            if (p.status === 'completed') {
              message.success(`模型下载完成`);
              loadModels();
            } else {
              message.error(`下载失败: ${p.error}`);
            }
          }
        } catch {
          clearInterval(timer);
          delete pollTimerRef.current[modelId];
        }
      }, 1500);
      pollTimerRef.current[modelId] = timer;
    } catch (err: any) {
      message.error(err.message || '下载启动失败');
    }
  };

  const handleDelete = async (modelId: string) => {
    try {
      await api.models.deleteModel(modelId);
      message.success('模型已删除');
      loadModels();
    } catch (err: any) {
      message.error(err.message || '删除失败');
    }
  };

  const handleActivate = async (modelId: string) => {
    try {
      await api.models.activateModel(modelId);
      message.success('模型已启用');
      loadModels();
      loadConfig(); // 刷新配置以更新 asr_model_id
    } catch (err: any) {
      message.error(err.message || '启用失败');
    }
  };

  // ── 保存操作 ──

  const handleSaveAll = async () => {
    try {
      const values = await form.validateFields();
      setSavingAll(true);
      await api.config.updateConfig(values as SystemConfig);
      message.success('配置保存成功');
    } catch (err: any) {
      if (err.errorFields) {
        message.error('请检查表单填写是否正确');
      } else {
        message.error(err.message || '保存配置失败');
      }
    } finally {
      setSavingAll(false);
    }
  };

  const handleSaveEmby = async () => {
    try {
      await form.validateFields(['emby_url', 'emby_api_key']);
      const embyConfig = {
        emby_url: form.getFieldValue('emby_url'),
        emby_api_key: form.getFieldValue('emby_api_key'),
      };
      setSavingEmby(true);
      await api.config.partialUpdateConfig(embyConfig);
      message.success('Emby 配置保存成功');
    } catch (err: any) {
      if (err.errorFields) message.error('请检查 Emby 配置');
      else message.error(err.message || '保存失败');
    } finally {
      setSavingEmby(false);
    }
  };

  const handleSaveTranslation = async () => {
    try {
      const service = form.getFieldValue('translation_service');
      const fieldsToValidate = ['translation_service'];
      if (service === 'openai') fieldsToValidate.push('openai_api_key', 'openai_model');
      else if (service === 'deepseek') fieldsToValidate.push('deepseek_api_key');
      else if (service === 'local') fieldsToValidate.push('local_llm_url');

      await form.validateFields(fieldsToValidate);

      const translationConfig: any = { translation_service: service };
      if (service === 'openai') {
        translationConfig.openai_api_key = form.getFieldValue('openai_api_key');
        translationConfig.openai_model = form.getFieldValue('openai_model');
      } else if (service === 'deepseek') {
        translationConfig.deepseek_api_key = form.getFieldValue('deepseek_api_key');
      } else if (service === 'local') {
        translationConfig.local_llm_url = form.getFieldValue('local_llm_url');
      }

      setSavingTranslation(true);
      await api.config.partialUpdateConfig(translationConfig);
      message.success('翻译服务配置保存成功');
    } catch (err: any) {
      if (err.errorFields) message.error('请检查翻译服务配置');
      else message.error(err.message || '保存失败');
    } finally {
      setSavingTranslation(false);
    }
  };

  // ── 测试连接 ──

  const handleTestEmby = async () => {
    const embyUrl = form.getFieldValue('emby_url');
    const embyApiKey = form.getFieldValue('emby_api_key');
    if (!embyUrl || !embyApiKey) { message.warning('请先填写 Emby URL 和 API Key'); return; }
    setTestingEmby(true);
    try {
      const result = await api.config.testEmby({ emby_url: embyUrl, emby_api_key: embyApiKey });
      result.success ? message.success(result.message) : message.error(result.message);
    } catch (err: any) {
      message.error(err.message || '测试失败');
    } finally {
      setTestingEmby(false);
    }
  };

  const handleTestTranslation = async () => {
    const service = form.getFieldValue('translation_service');
    if (!service) { message.warning('请先选择翻译服务'); return; }
    const openaiApiKey = form.getFieldValue('openai_api_key');
    const deepseekApiKey = form.getFieldValue('deepseek_api_key');
    const localLlmUrl = form.getFieldValue('local_llm_url');
    if (service === 'openai' && !openaiApiKey) { message.warning('请先填写 OpenAI API Key'); return; }
    if (service === 'deepseek' && !deepseekApiKey) { message.warning('请先填写 DeepSeek API Key'); return; }
    if (service === 'local' && !localLlmUrl) { message.warning('请先填写本地 LLM URL'); return; }

    setTestingTranslation(true);
    try {
      const result = await api.config.testTranslation({
        translation_service: service,
        api_key: service === 'openai' ? openaiApiKey : service === 'deepseek' ? deepseekApiKey : undefined,
        api_url: service === 'local' ? localLlmUrl : undefined,
        model: service === 'openai' ? form.getFieldValue('openai_model') : undefined,
      });
      result.success ? message.success(result.message) : message.error(result.message);
    } catch (err: any) {
      message.error(err.message || '测试失败');
    } finally {
      setTestingTranslation(false);
    }
  };

  // ── 模型表格列定义 ──

  const modelColumns = [
    {
      title: '模型名称',
      dataIndex: 'name',
      key: 'name',
      width: 260,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: string) => (
        <Tag color={type === 'online' ? 'blue' : 'green'}>
          {type === 'online' ? '流式' : '离线'}
        </Tag>
      ),
    },
    {
      title: '支持语言',
      dataIndex: 'languages',
      key: 'languages',
      width: 200,
      render: (langs: string[]) => (
        <Space size={[0, 4]} wrap>
          {langs.slice(0, 5).map(l => (
            <Tag key={l} style={{ margin: 0 }}>{LANG_LABELS[l] || l}</Tag>
          ))}
          {langs.length > 5 && <Tag>+{langs.length - 5}</Tag>}
        </Space>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 100,
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_: any, record: ASRModel) => {
        if (record.active) return <Tag color="success">使用中</Tag>;
        if (record.installed) return <Tag color="processing">已安装</Tag>;
        return <Tag>未安装</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: ASRModel) => {
        const dl = downloadingModels[record.id];
        const isDownloading = dl && (dl.status === 'downloading' || dl.status === 'extracting');

        if (isDownloading) {
          return (
            <Progress
              percent={dl!.progress}
              size="small"
              status={dl!.status === 'extracting' ? 'active' : 'normal'}
              format={p => dl!.status === 'extracting' ? '解压中' : `${p}%`}
              style={{ width: 140 }}
            />
          );
        }

        return (
          <Space>
            {!record.installed && (
              <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(record.id)}>
                下载
              </Button>
            )}
            {record.installed && !record.active && (
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleActivate(record.id)}>
                启用
              </Button>
            )}
            {record.installed && !record.active && (
              <Popconfirm title="确定删除该模型？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
                <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>
            )}
          </Space>
        );
      },
    },
  ];

  // ── 渲染 ──

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" tip="加载配置中..." />
      </div>
    );
  }

  return (
    <div>
      <h1>Settings</h1>

      {error && (
        <Alert
          message="错误"
          description={error}
          type="error"
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 24 }}
        />
      )}

      <Form form={form} layout="vertical" autoComplete="off">
        {/* Emby 配置 */}
        <Card
          title={<Space><ApiOutlined />Emby 服务器配置</Space>}
          style={{ marginBottom: 24 }}
          extra={
            <Space>
              <Button icon={<CheckCircleOutlined />} loading={testingEmby} onClick={handleTestEmby}>
                测试连接
              </Button>
              <Button type="primary" icon={<SaveOutlined />} loading={savingEmby} onClick={handleSaveEmby}>
                保存 Emby 配置
              </Button>
            </Space>
          }
        >
          <Form.Item
            label="Emby Server URL" name="emby_url"
            rules={[{ required: true, message: '请输入 Emby Server URL' }, { type: 'url', message: '请输入有效的 URL' }]}
            extra="例如: http://localhost:8096"
          >
            <Input placeholder="http://localhost:8096" />
          </Form.Item>
          <Form.Item
            label="API Key" name="emby_api_key"
            rules={[{ required: true, message: '请输入 Emby API Key' }]}
            extra="在 Emby 设置 > API 密钥中生成"
          >
            <Input.Password placeholder="输入 API Key" />
          </Form.Item>
        </Card>

        {/* ASR 模型管理 */}
        <Card
          title={<Space><CloudServerOutlined />ASR 模型管理</Space>}
          style={{ marginBottom: 24 }}
          extra={
            <Button onClick={loadModels} loading={modelsLoading}>
              刷新
            </Button>
          }
        >
          <p style={{ marginBottom: 16, color: '#666' }}>
            选择并下载 ASR 模型。流式模型适合实时场景，离线模型（如 Whisper）精度更高。
          </p>
          <Table
            dataSource={models}
            columns={modelColumns}
            rowKey="id"
            loading={modelsLoading}
            pagination={false}
            size="small"
          />
        </Card>

        {/* ASR 引擎配置 */}
        <Card title="ASR 引擎配置" style={{ marginBottom: 24 }}>
          <Form.Item
            label="ASR 引擎类型" name="asr_engine"
            rules={[{ required: true, message: '请选择 ASR 引擎类型' }]}
          >
            <Select placeholder="选择 ASR 引擎">
              <Option value="sherpa-onnx">Sherpa-ONNX (本地)</Option>
              <Option value="cloud">云端 ASR</Option>
            </Select>
          </Form.Item>

          {asrEngine === 'sherpa-onnx' && (
            <>
              <Form.Item label="当前模型" name="asr_model_id">
                <Select placeholder="从上方模型列表中选择并启用" allowClear>
                  {models.filter(m => m.installed).map(m => (
                    <Option key={m.id} value={m.id}>{m.name}</Option>
                  ))}
                </Select>
              </Form.Item>
              <Collapse
                ghost
                items={[{
                  key: 'advanced',
                  label: '高级选项：手动指定模型路径',
                  children: (
                    <Form.Item
                      label="模型路径" name="asr_model_path"
                      extra="手动指定模型目录（优先级低于上方模型选择）"
                    >
                      <Input placeholder="/path/to/sherpa-onnx-model" />
                    </Form.Item>
                  ),
                }]}
              />
            </>
          )}

          {asrEngine === 'cloud' && (
            <>
              <Form.Item
                label="云端 ASR URL" name="cloud_asr_url"
                rules={[{ required: true, message: '请输入云端 ASR URL' }, { type: 'url', message: '请输入有效的 URL' }]}
              >
                <Input placeholder="https://api.example.com/asr" />
              </Form.Item>
              <Form.Item
                label="云端 ASR API Key" name="cloud_asr_api_key"
                rules={[{ required: true, message: '请输入云端 ASR API Key' }]}
              >
                <Input.Password placeholder="输入 API Key" />
              </Form.Item>
            </>
          )}
        </Card>

        {/* 语言配置 */}
        <Card
          title={<Space><TranslationOutlined />语言配置</Space>}
          style={{ marginBottom: 24 }}
        >
          <Form.Item
            label="源语言（视频语音语言）" name="source_language"
            rules={[{ required: true, message: '请选择源语言' }]}
            initialValue="ja"
          >
            <Select placeholder="选择源语言" showSearch optionFilterProp="label">
              {(languages.length > 0 ? languages : Object.entries(LANG_LABELS).map(([code, name]) => ({ code, name }))).map(l => (
                <Option key={l.code} value={l.code} label={`${l.name} (${l.code})`}>
                  {l.name} ({l.code})
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            label="目标语言（字幕翻译语言）" name="target_language"
            rules={[{ required: true, message: '请选择目标语言' }]}
            initialValue="zh"
          >
            <Select placeholder="选择目标语言" showSearch optionFilterProp="label">
              {(languages.length > 0 ? languages : Object.entries(LANG_LABELS).map(([code, name]) => ({ code, name }))).map(l => (
                <Option key={l.code} value={l.code} label={`${l.name} (${l.code})`}>
                  {l.name} ({l.code})
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Card>

        {/* 翻译服务配置 */}
        <Card
          title={<Space><TranslationOutlined />翻译服务配置</Space>}
          style={{ marginBottom: 24 }}
          extra={
            <Space>
              <Button icon={<CheckCircleOutlined />} loading={testingTranslation} onClick={handleTestTranslation}>
                测试服务
              </Button>
              <Button type="primary" icon={<SaveOutlined />} loading={savingTranslation} onClick={handleSaveTranslation}>
                保存翻译配置
              </Button>
            </Space>
          }
        >
          <Form.Item
            label="翻译服务类型" name="translation_service"
            rules={[{ required: true, message: '请选择翻译服务类型' }]}
          >
            <Select placeholder="选择翻译服务">
              <Option value="openai">OpenAI</Option>
              <Option value="deepseek">DeepSeek</Option>
              <Option value="local">本地 LLM</Option>
            </Select>
          </Form.Item>

          {translationService === 'openai' && (
            <>
              <Form.Item label="OpenAI API Key" name="openai_api_key" rules={[{ required: true, message: '请输入 OpenAI API Key' }]}>
                <Input.Password placeholder="sk-..." />
              </Form.Item>
              <Form.Item label="OpenAI 模型" name="openai_model" rules={[{ required: true, message: '请输入模型名称' }]} initialValue="gpt-4">
                <Select>
                  <Option value="gpt-4">GPT-4</Option>
                  <Option value="gpt-4-turbo">GPT-4 Turbo</Option>
                  <Option value="gpt-3.5-turbo">GPT-3.5 Turbo</Option>
                </Select>
              </Form.Item>
            </>
          )}
          {translationService === 'deepseek' && (
            <Form.Item label="DeepSeek API Key" name="deepseek_api_key" rules={[{ required: true, message: '请输入 DeepSeek API Key' }]}>
              <Input.Password placeholder="输入 API Key" />
            </Form.Item>
          )}
          {translationService === 'local' && (
            <Form.Item
              label="本地 LLM URL" name="local_llm_url"
              rules={[{ required: true, message: '请输入本地 LLM URL' }, { type: 'url', message: '请输入有效的 URL' }]}
              extra="例如: http://localhost:11434 (Ollama)"
            >
              <Input placeholder="http://localhost:11434" />
            </Form.Item>
          )}
        </Card>

        {/* 任务配置 */}
        <Card title="任务配置" style={{ marginBottom: 24 }}>
          <Form.Item
            label="最大并发任务数" name="max_concurrent_tasks"
            rules={[{ required: true, message: '请输入最大并发任务数' }, { type: 'number', min: 1, max: 10, message: '请输入 1-10 之间的数字' }]}
            initialValue={2}
          >
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            label="临时文件目录" name="temp_dir"
            rules={[{ required: true, message: '请输入临时文件目录' }]}
            initialValue="/tmp/subtitle_service"
          >
            <Input placeholder="/tmp/subtitle_service" />
          </Form.Item>
        </Card>

        {/* 保存按钮 */}
        <Card>
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={savingAll} onClick={handleSaveAll} size="large">
              保存所有配置
            </Button>
            <Button onClick={() => form.resetFields()} disabled={savingAll || savingEmby || savingTranslation} size="large">
              重置
            </Button>
          </Space>
        </Card>
      </Form>
    </div>
  );
};

export default Settings;
