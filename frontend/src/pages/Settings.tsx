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
  Typography,
  Divider,
  Row,
  Col,
  Badge,
} from 'antd';
import {
  SaveOutlined,
  ApiOutlined,
  TranslationOutlined,
  CheckCircleFilled,
  DownloadOutlined,
  DeleteOutlined,
  PlayCircleFilled,
  CloudServerOutlined,
  SettingOutlined,
  GlobalOutlined,
  RocketOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { SystemConfig, ASRModel, ModelDownloadProgress, LanguageInfo } from '../types/api';

const { Option } = Select;
const { Text, Title, Paragraph } = Typography;

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

  const [models, setModels] = useState<ASRModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [downloadingModels, setDownloadingModels] = useState<Record<string, ModelDownloadProgress>>({});
  const pollTimerRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);

  const asrEngine = Form.useWatch('asr_engine', form);
  const translationService = Form.useWatch('translation_service', form);

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
    } catch { } finally {
      setModelsLoading(false);
    }
  }, []);

  const loadLanguages = useCallback(async () => {
    try {
      const data = await api.models.listLanguages();
      setLanguages(data);
    } catch { }
  }, []);

  useEffect(() => {
    loadConfig();
    loadModels();
    loadLanguages();
    return () => {
      Object.values(pollTimerRef.current).forEach(clearInterval);
    };
  }, [loadModels, loadLanguages]);

  const handleDownload = async (modelId: string) => {
    try {
      const progress = await api.models.downloadModel(modelId);
      setDownloadingModels(prev => ({ ...prev, [modelId]: progress }));
      const timer = setInterval(async () => {
        try {
          const p = await api.models.getDownloadProgress(modelId);
          setDownloadingModels(prev => ({ ...prev, [modelId]: p }));
          if (p.status === 'completed' || p.status === 'failed') {
            clearInterval(timer);
            delete pollTimerRef.current[modelId];
            if (p.status === 'completed') { message.success(`模型下载完成`); loadModels(); }
            else { message.error(`下载失败: ${p.error}`); }
          }
        } catch { clearInterval(timer); delete pollTimerRef.current[modelId]; }
      }, 1500);
      pollTimerRef.current[modelId] = timer;
    } catch (err: any) { message.error(err.message || '下载启动失败'); }
  };

  const handleDelete = async (modelId: string) => {
    try { await api.models.deleteModel(modelId); message.success('模型已删除'); loadModels(); }
    catch (err: any) { message.error(err.message || '删除失败'); }
  };

  const handleActivate = async (modelId: string) => {
    try { await api.models.activateModel(modelId); message.success('模型已启用'); loadModels(); loadConfig(); }
    catch (err: any) { message.error(err.message || '启用失败'); }
  };

  const handleSaveAll = async () => {
    try {
      const values = await form.validateFields();
      setSavingAll(true);
      await api.config.updateConfig(values as SystemConfig);
      message.success('配置保存成功');
    } catch (err: any) {
      if (err.errorFields) message.error('请检查表单填写是否正确');
      else message.error(err.message || '保存配置失败');
    } finally { setSavingAll(false); }
  };

  const handleSaveEmby = async () => {
    try {
      await form.validateFields(['emby_url', 'emby_api_key']);
      setSavingEmby(true);
      await api.config.partialUpdateConfig({
        emby_url: form.getFieldValue('emby_url'),
        emby_api_key: form.getFieldValue('emby_api_key'),
      });
      message.success('Emby 配置保存成功');
    } catch (err: any) {
      if (err.errorFields) message.error('请检查 Emby 配置');
      else message.error(err.message || '保存失败');
    } finally { setSavingEmby(false); }
  };

  const handleSaveTranslation = async () => {
    try {
      const service = form.getFieldValue('translation_service');
      const fields = ['translation_service'];
      if (service === 'openai') fields.push('openai_api_key', 'openai_model');
      else if (service === 'deepseek') fields.push('deepseek_api_key');
      else if (service === 'local') fields.push('local_llm_url');
      await form.validateFields(fields);
      const config: any = { translation_service: service };
      if (service === 'openai') { config.openai_api_key = form.getFieldValue('openai_api_key'); config.openai_model = form.getFieldValue('openai_model'); }
      else if (service === 'deepseek') { config.deepseek_api_key = form.getFieldValue('deepseek_api_key'); }
      else if (service === 'local') { config.local_llm_url = form.getFieldValue('local_llm_url'); }
      setSavingTranslation(true);
      await api.config.partialUpdateConfig(config);
      message.success('翻译服务配置保存成功');
    } catch (err: any) {
      if (err.errorFields) message.error('请检查翻译服务配置');
      else message.error(err.message || '保存失败');
    } finally { setSavingTranslation(false); }
  };

  const handleTestEmby = async () => {
    const url = form.getFieldValue('emby_url'), key = form.getFieldValue('emby_api_key');
    if (!url || !key) { message.warning('请先填写 Emby URL 和 API Key'); return; }
    setTestingEmby(true);
    try { const res = await api.config.testEmby({ emby_url: url, emby_api_key: key }); res.success ? message.success(res.message) : message.error(res.message); }
    catch (err: any) { message.error(err.message || '测试失败'); } finally { setTestingEmby(false); }
  };

  const handleTestTranslation = async () => {
    const service = form.getFieldValue('translation_service');
    if (!service) { message.warning('请先选择翻译服务'); return; }
    setTestingTranslation(true);
    try {
      const res = await api.config.testTranslation({
        translation_service: service,
        api_key: service === 'openai' ? form.getFieldValue('openai_api_key') : service === 'deepseek' ? form.getFieldValue('deepseek_api_key') : undefined,
        api_url: service === 'local' ? form.getFieldValue('local_llm_url') : undefined,
        model: service === 'openai' ? form.getFieldValue('openai_model') : undefined,
      });
      res.success ? message.success(res.message) : message.error(res.message);
    } catch (err: any) { message.error(err.message || '测试失败'); } finally { setTestingTranslation(false); }
  };

  const modelColumns = [
    { title: '模型名称', dataIndex: 'name', key: 'name', render: (text: string) => <Text strong style={{ color: 'rgba(255,255,255,0.85)' }}>{text}</Text> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 90, render: (t: string) => <Tag color={t === 'online' ? 'blue' : 'green'} style={{ borderRadius: 4 }}>{t === 'online' ? '流式' : '离线'}</Tag> },
    { title: '语言', dataIndex: 'languages', key: 'languages', width: 180, render: (ls: string[]) => <Space size={[0, 4]} wrap>{ls.slice(0, 3).map(l => <Tag key={l} style={{ fontSize: 10, margin: 0 }}>{LANG_LABELS[l] || l}</Tag>)}{ls.length > 3 && <Tag style={{ fontSize: 10 }}>+{ls.length - 3}</Tag>}</Space> },
    { title: '大小', dataIndex: 'size', key: 'size', width: 90, render: (s: string) => <Text type="secondary" style={{ fontSize: 12 }}>{s}</Text> },
    { title: '状态', key: 'status', width: 100, render: (_: any, r: ASRModel) => r.active ? <Badge status="success" text="活跃" /> : (r.installed ? <Badge status="processing" text="就绪" /> : <Badge status="default" text="未安装" />) },
    { title: '操作', key: 'action', width: 160, align: 'right' as const, render: (_: any, r: ASRModel) => {
      const dl = downloadingModels[r.id], isDl = dl && (dl.status === 'downloading' || dl.status === 'extracting');
      if (isDl) return <Progress percent={dl!.progress} size="small" format={p => dl!.status === 'extracting' ? '解压' : `${p}%`} style={{ width: 100 }} />;
      return (
        <Space>
          {!r.installed && <Button size="small" type="link" icon={<DownloadOutlined />} onClick={() => handleDownload(r.id)}>下载</Button>}
          {r.installed && !r.active && <Button size="small" type="link" icon={<PlayCircleFilled />} onClick={() => handleActivate(r.id)}>启用</Button>}
          {r.installed && !r.active && <Popconfirm title="确定删除？" onConfirm={() => handleDelete(r.id)}><Button size="small" type="link" danger icon={<DeleteOutlined />} /></Popconfirm>}
        </Space>
      );
    }},
  ];

  if (loading) return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" tip="同步系统设置..." /></div>;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', paddingBottom: 60 }}>
      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 24, borderRadius: 12 }} />}

      <Form form={form} layout="vertical" autoComplete="off" requiredMark={false}>
        <Row gutter={[24, 24]}>
          {/* Left Column */}
          <Col xs={24} lg={14}>
            <Space direction="vertical" size={24} style={{ width: '100%' }}>
              {/* Emby Section */}
              <Card className="glass-card" title={<Space><ApiOutlined />Emby 服务器连接</Space>} extra={
                <Space>
                  <Button type="text" loading={testingEmby} onClick={handleTestEmby}>测试</Button>
                  <Button type="primary" size="small" loading={savingEmby} onClick={handleSaveEmby}>保存</Button>
                </Space>
              }>
                <Row gutter={16}>
                  <Col span={14}>
                    <Form.Item label="服务器地址" name="emby_url" rules={[{ required: true, type: 'url' }]}>
                      <Input placeholder="http://192.168.1.100:8096" />
                    </Form.Item>
                  </Col>
                  <Col span={10}>
                    <Form.Item label="API 密钥" name="emby_api_key" rules={[{ required: true }]}>
                      <Input.Password placeholder="密钥" />
                    </Form.Item>
                  </Col>
                </Row>
              </Card>

              {/* Model Management */}
              <Card className="glass-card" title={<Space><CloudServerOutlined />ASR 模型库</Space>} extra={
                <Button type="text" icon={<ReloadOutlined />} onClick={loadModels} loading={modelsLoading} />
              } bodyStyle={{ padding: 0 }}>
                <div style={{ padding: '12px 24px' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>选择适合您硬件的语音识别模型。Whisper 系列模型推荐使用离线安装以获得最佳效果。</Text>
                </div>
                <Table dataSource={models} columns={modelColumns} rowKey="id" loading={modelsLoading} pagination={false} size="middle" className="custom-table" />
              </Card>

              {/* ASR Configuration */}
              <Card className="glass-card" title={<Space><SettingOutlined />识别引擎设置</Space>}>
                <Form.Item label="引擎类型" name="asr_engine" rules={[{ required: true }]}>
                  <Select>
                    <Option value="sherpa-onnx">Sherpa-ONNX (推荐本地部署)</Option>
                    <Option value="cloud">外部云端 API (极速识别)</Option>
                  </Select>
                </Form.Item>
                {asrEngine === 'cloud' && (
                  <Row gutter={16}>
                    <Col span={12}><Form.Item label="API URL" name="cloud_asr_url" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item></Col>
                    <Col span={12}><Form.Item label="API Key" name="cloud_asr_api_key" rules={[{ required: true }]}><Input.Password /></Form.Item></Col>
                  </Row>
                )}
              </Card>
            </Space>
          </Col>

          {/* Right Column */}
          <Col xs={24} lg={10}>
            <Space direction="vertical" size={24} style={{ width: '100%' }}>
              {/* Language Section */}
              <Card className="glass-card" title={<Space><GlobalOutlined />多语言偏好</Space>}>
                <Form.Item label="视频原声语言" name="source_language" rules={[{ required: true }]}>
                  <Select showSearch optionFilterProp="label">
                    {Object.entries(LANG_LABELS).map(([c, n]) => <Option key={c} value={c} label={n}>{n} ({c})</Option>)}
                  </Select>
                </Form.Item>
                <Form.Item label="字幕翻译目标" name="target_language" rules={[{ required: true }]}>
                  <Select showSearch optionFilterProp="label">
                    {Object.entries(LANG_LABELS).map(([c, n]) => <Option key={c} value={c} label={n}>{n} ({c})</Option>)}
                  </Select>
                </Form.Item>
              </Card>

              {/* Translation Section */}
              <Card className="glass-card" title={<Space><TranslationOutlined />翻译服务引擎</Space>} extra={
                <Space>
                  <Button type="text" loading={testingTranslation} onClick={handleTestTranslation}>测试</Button>
                  <Button type="primary" size="small" loading={savingTranslation} onClick={handleSaveTranslation}>保存</Button>
                </Space>
              }>
                <Form.Item label="服务提供商" name="translation_service" rules={[{ required: true }]}>
                  <Select>
                    <Option value="openai">OpenAI (GPT-4)</Option>
                    <Option value="deepseek">DeepSeek (性价比首选)</Option>
                    <Option value="local">本地自定义模型 (LLM)</Option>
                  </Select>
                </Form.Item>
                {translationService === 'openai' && (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item label="OpenAI API Key" name="openai_api_key" rules={[{ required: true }]}><Input.Password /></Form.Item>
                    <Form.Item label="模型名称" name="openai_model" rules={[{ required: true }]} initialValue="gpt-4"><Input /></Form.Item>
                  </Space>
                )}
                {translationService === 'deepseek' && <Form.Item label="DeepSeek API Key" name="deepseek_api_key" rules={[{ required: true }]}><Input.Password /></Form.Item>}
                {translationService === 'local' && <Form.Item label="本地模型 Endpoint" name="local_llm_url" rules={[{ required: true, type: 'url' }]}><Input placeholder="http://localhost:11434" /></Form.Item>}
              </Card>

              {/* Task Config */}
              <Card className="glass-card" title={<Space><RocketOutlined />性能与调度</Space>}>
                <Form.Item label="最大并行任务数" name="max_concurrent_tasks" rules={[{ required: true }]}>
                  <InputNumber min={1} max={10} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item label="工作缓存路径" name="temp_dir" rules={[{ required: true }]}>
                  <Input placeholder="/tmp/subtitle_service" />
                </Form.Item>
              </Card>

              <div style={{ textAlign: 'right', marginTop: 12 }}>
                <Space size="middle">
                  <Button size="large" onClick={() => form.resetFields()}>重置修改</Button>
                  <Button type="primary" size="large" icon={<SaveOutlined />} loading={savingAll} onClick={handleSaveAll} style={{ paddingLeft: 40, paddingRight: 40, boxShadow: '0 4px 15px rgba(22, 119, 255, 0.4)' }}>
                    保存全部设置
                  </Button>
                </Space>
              </div>
            </Space>
          </Col>
        </Row>
      </Form>

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-table .ant-table { background: transparent !important; }
        .custom-table .ant-table-thead > tr > th { 
          background: rgba(255,255,255,0.02) !important; 
          border-bottom: 1px solid rgba(255,255,255,0.05) !important;
          color: rgba(255,255,255,0.45) !important;
          font-size: 12px;
        }
        .custom-table .ant-table-tbody > tr > td { 
          border-bottom: 1px solid rgba(255,255,255,0.03) !important; 
        }
        .custom-table .ant-table-tbody > tr:hover > td {
          background: rgba(255,255,255,0.02) !important;
        }
        .ant-form-item-label > label {
          color: rgba(255,255,255,0.45) !important;
          font-size: 13px !important;
        }
        .ant-collapse {
          background: transparent !important;
          border: none !important;
        }
      `}} />
    </div>
  );
};

export default Settings;
