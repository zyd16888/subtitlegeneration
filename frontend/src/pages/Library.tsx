import React, { useState, useEffect } from 'react';
import {
  Card,
  Row,
  Col,
  Select,
  Input,
  message,
  Spin,
  Alert,
  Pagination,
  Empty,
  Button,
} from 'antd';
import {
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { Library, MediaItem, TaskConfig } from '../types/api';
import SeriesEpisodesModal from '../components/SeriesEpisodesModal';
import MediaConfigModal from '../components/MediaConfigModal';

const { Search } = Input;
const { Option } = Select;

/**
 * 媒体项卡片图片组件
 * 自动适应竖版和横版图片，根据实际图片比例动态调整容器
 */
const MediaItemImage: React.FC<{
  imageUrl?: string;
  name: string;
  hasSubtitles: boolean;
}> = ({ imageUrl, name, hasSubtitles }) => {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [aspectRatio, setAspectRatio] = useState<number>(1.5); // 默认 2:3

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const ratio = img.naturalHeight / img.naturalWidth;
    setAspectRatio(ratio);
    setImageLoaded(true);
  };

  const handleImageError = () => {
    setImageError(true);
  };

  // 根据图片实际比例设置容器高度
  // 限制最小和最大比例，避免过于极端
  const minRatio = 0.5; // 最扁（2:1）
  const maxRatio = 1.8; // 最高（接近 2:3）
  const clampedRatio = Math.max(minRatio, Math.min(maxRatio, aspectRatio));
  const containerPaddingTop = `${clampedRatio * 100}%`;

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        paddingTop: containerPaddingTop,
        background: '#1a1a1a',
        overflow: 'hidden',
        transition: 'padding-top 0.3s ease',
      }}
    >
      {imageUrl && !imageError ? (
        <img
          src={imageUrl}
          alt={name}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            opacity: imageLoaded ? 1 : 0,
            transition: 'opacity 0.3s ease',
          }}
          onLoad={handleImageLoad}
          onError={handleImageError}
        />
      ) : null}
      {(!imageUrl || imageError) && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#f0f0f0',
          }}
        >
          <PlayCircleOutlined style={{ fontSize: 36, color: '#ccc' }} />
        </div>
      )}
      <div
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          zIndex: 1,
          background: 'rgba(0, 0, 0, 0.7)',
          borderRadius: '50%',
          padding: '2px',
        }}
      >
        {hasSubtitles ? (
          <CheckCircleOutlined
            style={{ fontSize: 20, color: '#52c41a' }}
            title="已有字幕"
          />
        ) : (
          <CloseCircleOutlined
            style={{ fontSize: 20, color: '#ff4d4f' }}
            title="无字幕"
          />
        )}
      </div>
    </div>
  );
};

/**
 * Library 页面
 * 
 * 浏览和管理 Emby 媒体库
 * - 显示媒体库筛选器（媒体库、类型、搜索）
 * - 显示媒体项网格视图（缩略图、标题、字幕状态）
 * - 点击媒体项打开配置对话框
 * - 剧集显示为单个卡片，点击展开查看集数
 * - 电影等单个媒体项点击打开配置对话框
 * - 实现分页功能
 * 
 * 需求: 9.1, 9.2, 9.3, 9.4, 9.5, 15.1, 20.1
 */
const LibraryPage: React.FC = () => {
  // 状态管理
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
  const [selectedLibrary, setSelectedLibrary] = useState<string | undefined>(undefined);
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  const [searchText, setSearchText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embyConfigured, setEmbyConfigured] = useState(true);
  const [configValid, setConfigValid] = useState(true);
  const [configMessage, setConfigMessage] = useState<string>('');

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // 剧集详情对话框状态
  const [seriesModalVisible, setSeriesModalVisible] = useState(false);
  const [selectedSeries, setSelectedSeries] = useState<{ id: string; name: string } | null>(null);

  // 单个媒体项配置对话框状态
  const [mediaConfigModalVisible, setMediaConfigModalVisible] = useState(false);
  const [selectedMediaItem, setSelectedMediaItem] = useState<MediaItem | null>(null);

  // 获取媒体库列表
  const fetchLibraries = async () => {
    try {
      const data = await api.media.getLibraries();
      setLibraries(data);
      setEmbyConfigured(true);
    } catch (err: any) {
      console.error('获取媒体库列表失败:', err);
      // 检查是否是配置问题
      if (err.message && (err.message.includes('Emby') || err.message.includes('配置'))) {
        setEmbyConfigured(false);
      } else {
        message.error('获取媒体库列表失败');
      }
    }
  };

  // 验证系统配置
  const validateConfig = async () => {
    try {
      const result = await api.config.validateConfig();
      setConfigValid(result.is_valid);
      setConfigMessage(result.message);
    } catch (err: any) {
      console.error('验证配置失败:', err);
      // 如果验证失败，假设配置不完整
      setConfigValid(false);
      setConfigMessage('无法验证配置，请检查系统设置');
    }
  };

  // 获取媒体项列表
  const fetchMediaItems = async () => {
    // 如果 Emby 未配置或未选择媒体库，不加载媒体项
    if (!embyConfigured || !selectedLibrary) {
      setMediaItems([]);
      setTotal(0);
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const response = await api.media.getMediaItems({
        library_id: selectedLibrary,
        item_type: selectedType,
        search: searchText || undefined,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
      });
      setMediaItems(response.items);
      setTotal(response.total);
    } catch (err: any) {
      setError(err.message || '获取媒体项失败');
      message.error('获取媒体项失败');
    } finally {
      setLoading(false);
    }
  };

  // 初始加载媒体库列表
  useEffect(() => {
    fetchLibraries();
    validateConfig();
  }, []);

  // 当筛选条件或分页改变时重新加载媒体项
  useEffect(() => {
    fetchMediaItems();
  }, [selectedLibrary, selectedType, searchText, currentPage, pageSize]);

  // 处理搜索
  const handleSearch = (value: string) => {
    setSearchText(value);
    setCurrentPage(1); // 重置到第一页
  };

  // 处理媒体库筛选
  const handleLibraryChange = (value: string | undefined) => {
    setSelectedLibrary(value);
    setCurrentPage(1);
  };

  // 处理类型筛选
  const handleTypeChange = (value: string | undefined) => {
    setSelectedType(value);
    setCurrentPage(1);
  };

  // 处理媒体项点击
  const handleItemClick = (item: MediaItem) => {
    // 如果是剧集，打开剧集详情对话框
    if (item.type === 'Series') {
      setSelectedSeries({ id: item.id, name: item.name });
      setSeriesModalVisible(true);
    } else {
      // 其他类型（电影、单集等）打开配置对话框
      setSelectedMediaItem(item);
      setMediaConfigModalVisible(true);
    }
  };

  // 处理单个媒体项生成字幕
  const handleMediaItemGenerateSubtitle = async (task: TaskConfig) => {
    // 检查配置是否完整
    if (!configValid) {
      message.warning('配置不完整，无法生成字幕。请先完成系统配置。');
      return;
    }
    
    try {
      await api.tasks.createTasks({
        tasks: [task],
      });
      message.success('成功创建字幕生成任务');
    } catch (err: any) {
      message.error(err.message || '创建任务失败');
    }
  };

  // 处理剧集生成字幕（单独配置）
  const handleSeriesGenerateSubtitles = async (tasks: TaskConfig[]) => {
    // 检查配置是否完整
    if (!configValid) {
      message.warning('配置不完整，无法生成字幕。请先完成系统配置。');
      return;
    }
    
    try {
      await api.tasks.createTasks({
        tasks,
      });
      message.success(`成功创建 ${tasks.length} 个字幕生成任务`);
    } catch (err: any) {
      message.error(err.message || '创建任务失败');
    }
  };

  // 处理分页改变
  const handlePageChange = (page: number, pageSize: number) => {
    setCurrentPage(page);
    setPageSize(pageSize);
  };

  // 媒体类型选项
  const mediaTypes = [
    { label: '全部', value: undefined },
    { label: '电影', value: 'Movie' },
    { label: '剧集', value: 'Series' },
    { label: '单集', value: 'Episode' },
  ];

  return (
    <div>
      <h1>Library</h1>

      {!embyConfigured && (
        <Alert
          message="Emby 未配置"
          description={
            <div>
              请先在设置页面配置 Emby 服务器信息后再使用媒体库功能。
              <br />
              <Button
                type="link"
                style={{ padding: 0, marginTop: 8 }}
                onClick={() => window.location.href = '/settings'}
              >
                前往设置页面
              </Button>
            </div>
          }
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      {!configValid && embyConfigured && (
        <Alert
          message="配置不完整"
          description={
            <div>
              {configMessage}
              <br />
              字幕生成功能不可用，请先完成相关配置。
              <br />
              <Button
                type="link"
                style={{ padding: 0, marginTop: 8 }}
                onClick={() => window.location.href = '/settings'}
              >
                前往设置页面
              </Button>
            </div>
          }
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

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

      {embyConfigured && (
        <>
          {/* 筛选器 */}
          <Card style={{ marginBottom: 24 }}>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} md={8}>
                <div style={{ marginBottom: 8, fontWeight: 'bold' }}>媒体库</div>
                <Select
                  style={{ width: '100%' }}
                  placeholder="选择媒体库"
                  allowClear
                  value={selectedLibrary}
                  onChange={handleLibraryChange}
                >
                  {libraries.map((lib) => (
                    <Option key={lib.id} value={lib.id}>
                      {lib.name}
                    </Option>
                  ))}
                </Select>
              </Col>
              <Col xs={24} sm={12} md={8}>
                <div style={{ marginBottom: 8, fontWeight: 'bold' }}>类型</div>
                <Select
                  style={{ width: '100%' }}
                  placeholder="选择类型"
                  value={selectedType}
                  onChange={handleTypeChange}
                >
                  {mediaTypes.map((type) => (
                    <Option key={type.value || 'all'} value={type.value}>
                      {type.label}
                    </Option>
                  ))}
                </Select>
              </Col>
              <Col xs={24} sm={24} md={8}>
                <div style={{ marginBottom: 8, fontWeight: 'bold' }}>搜索</div>
                <Search
                  placeholder="搜索媒体项名称"
                  allowClear
                  enterButton={<SearchOutlined />}
                  onSearch={handleSearch}
                />
              </Col>
            </Row>
          </Card>

          {/* 媒体项网格 */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '50px' }}>
              <Spin size="large" tip="加载中..." />
            </div>
          ) : !selectedLibrary ? (
            <Card>
              <Empty description="请先选择一个媒体库" />
            </Card>
          ) : mediaItems.length === 0 ? (
            <Card>
              <Empty description="暂无媒体项" />
            </Card>
          ) : (
            <>
              <Row gutter={[12, 12]}>
                {mediaItems.map((item) => (
                  <Col key={item.id} xs={12} sm={8} md={6} lg={4} xl={3}>
                    <Card
                      hoverable
                      size="small"
                      style={{
                        border: '1px solid #f0f0f0',
                        cursor: 'pointer',
                      }}
                      styles={{ body: { padding: '8px' } }}
                      onClick={() => handleItemClick(item)}
                      cover={
                        <MediaItemImage
                          imageUrl={item.image_url}
                          name={item.name}
                          hasSubtitles={item.has_subtitles}
                        />
                      }
                    >
                      <Card.Meta
                        title={
                          <div
                            style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              fontSize: '13px',
                            }}
                            title={item.name}
                          >
                            {item.name}
                          </div>
                        }
                        description={
                          <div style={{ fontSize: 11, color: '#999' }}>
                            {item.type === 'Series' ? '剧集 (点击查看)' : `${item.type} (点击配置)`}
                          </div>
                        }
                      />
                    </Card>
                  </Col>
                ))}
              </Row>

              {/* 分页 */}
              <div style={{ marginTop: 24, textAlign: 'center' }}>
                <Pagination
                  current={currentPage}
                  pageSize={pageSize}
                  total={total}
                  onChange={handlePageChange}
                  showSizeChanger
                  showQuickJumper
                  showTotal={(total) => `共 ${total} 项`}
                  pageSizeOptions={['10', '20', '50', '100']}
                />
              </div>
            </>
          )}
        </>
      )}

      {/* 剧集详情对话框 */}
      {selectedSeries && (
        <SeriesEpisodesModal
          visible={seriesModalVisible}
          seriesId={selectedSeries.id}
          seriesName={selectedSeries.name}
          configValid={configValid}
          configMessage={configMessage}
          onClose={() => {
            setSeriesModalVisible(false);
            setSelectedSeries(null);
          }}
          onGenerateSubtitles={handleSeriesGenerateSubtitles}
        />
      )}

      {/* 单个媒体项配置对话框 */}
      {selectedMediaItem && (
        <MediaConfigModal
          visible={mediaConfigModalVisible}
          mediaItem={selectedMediaItem}
          configValid={configValid}
          configMessage={configMessage}
          onClose={() => {
            setMediaConfigModalVisible(false);
            setSelectedMediaItem(null);
          }}
          onGenerateSubtitle={handleMediaItemGenerateSubtitle}
        />
      )}
    </div>
  );
};

export default LibraryPage;
