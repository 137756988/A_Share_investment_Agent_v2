import React, { useState, useEffect } from 'react';
import { Input, Button, Card, Typography, Spin, message, Layout, Space, Tag, Divider, Tabs, Empty, List, Table, Tooltip } from 'antd';
import { SearchOutlined, LineChartOutlined, BarChartOutlined, BulbOutlined, ThunderboltOutlined, FileTextOutlined, DownloadOutlined, FileOutlined, ClockCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { askAgent, getStockReport, getReportsList, getReportDownloadUrl } from './api';
import ReactMarkdown from 'react-markdown';
import dayjs from 'dayjs';

const { Title, Paragraph, Text } = Typography;
const { Header, Content, Footer } = Layout;
const { TabPane } = Tabs;

export default function App() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [queryHistory, setQueryHistory] = useState(['贵州茅台的股票价值', '平安银行是否值得买入', '000858最近的技术分析']);
  
  // 新增状态
  const [stockCode, setStockCode] = useState('');
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('analysis');
  const [allReports, setAllReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(false);

  // 首次加载时获取报告列表
  useEffect(() => {
    loadReportsList();
  }, []);

  // 获取所有报告列表
  const loadReportsList = async () => {
    setReportsLoading(true);
    try {
      const reports = await getReportsList();
      setAllReports(reports);
    } catch (error) {
      console.error('加载报告列表失败', error);
    } finally {
      setReportsLoading(false);
    }
  };

  // 处理提交
  const handleSubmit = async () => {
    if (!query.trim()) {
      message.warning('请输入您的分析请求，如"贵州茅台的股票价值"');
      return;
    }
    setLoading(true);
    setResult('');
    try {
      const res = await askAgent(query);
      setResult(res);
      
      // 尝试从查询中提取股票代码
      const codeMatch = query.match(/\d{6}|\d{5}/g);
      if (codeMatch && codeMatch.length > 0) {
        const extractedCode = codeMatch[0];
        setStockCode(extractedCode);
        // 更新报告列表
        loadReportsList();
      }
      
      // 添加到查询历史
      if (!queryHistory.includes(query)) {
        setQueryHistory([query, ...queryHistory.slice(0, 4)]);
      }
    } catch (err) {
      message.error('请求失败，请检查后端服务是否启动');
      setResult('请求失败，请检查后端服务是否启动。');
    } finally {
      setLoading(false);
    }
  };

  // 下载报告
  const downloadReport = (ticker) => {
    const downloadUrl = getReportDownloadUrl(ticker);
    
    // 创建一个隐藏的a标签用于下载
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `股票${ticker}_分析报告.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    message.success(`开始下载股票${ticker}的分析报告`);
  };

  // 使用历史查询
  const useHistoryQuery = (historyQuery) => {
    setQuery(historyQuery);
  };

  // 按下Enter键时提交
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // 处理标签页切换
  const handleTabChange = (key) => {
    setActiveTab(key);
    if (key === 'reports') {
      loadReportsList();
    }
  };

  // 报告列表的列定义
  const reportsColumns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      render: (text, record) => (
        <Space>
          <FileOutlined style={{ color: '#1890ff' }} />
          <Tooltip title={text}>
            <span style={{ cursor: 'pointer' }}>
              {text.length > 30 ? text.substring(0, 30) + '...' : text}
            </span>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '股票代码',
      dataIndex: 'ticker',
      key: 'ticker',
      width: 100,
      render: (ticker) => <Tag color="blue">{ticker}</Tag>
    },
    {
      title: '生成时间',
      dataIndex: 'modified_time',
      key: 'modified_time',
      width: 180,
      render: (time) => (
        <Space>
          <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
          {dayjs(time * 1000).format('YYYY-MM-DD HH:mm:ss')}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space size="middle">
          <Button 
            type="primary" 
            size="small" 
            icon={<DownloadOutlined />}
            onClick={() => downloadReport(record.ticker)}
          >
            下载
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#1890ff', padding: '0 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', color: 'white' }}>
          <LineChartOutlined style={{ fontSize: 24, marginRight: 12 }} />
          <Title level={3} style={{ color: 'white', margin: 0 }}>A股智能投顾系统</Title>
        </div>
      </Header>
      <Content style={{ padding: '20px 50px' }}>
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          <Card 
            bordered={false} 
            style={{ borderRadius: 8, marginBottom: 20, boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}
          >
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Title level={4}>
                <BulbOutlined style={{ marginRight: 8, color: '#faad14' }} />
                智能投资分析
              </Title>
              
              <Paragraph>
                输入您的自然语言分析请求，系统将利用多Agent协作进行股票分析，提供投资建议。
              </Paragraph>
              
              <Input.TextArea
                rows={3}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder='请输入您的分析请求，例如"贵州茅台的股票价值"...'
                style={{ borderRadius: 4, fontSize: 16 }}
              />
              
              <Space wrap>
                <Text type="secondary">热门查询:</Text>
                {queryHistory.map((item, index) => (
                  <Tag 
                    key={index} 
                    color="blue" 
                    style={{ cursor: 'pointer' }}
                    onClick={() => useHistoryQuery(item)}
                  >
                    {item.length > 15 ? item.substring(0, 15) + '...' : item}
                  </Tag>
                ))}
              </Space>
              
              <Button 
                type="primary" 
                icon={<SearchOutlined />} 
                onClick={handleSubmit} 
                loading={loading} 
                size="large"
                style={{ borderRadius: 4, height: 48 }}
                block
              >
                开始分析
              </Button>
            </Space>
          </Card>
          
          <Card 
            bordered={false}
            style={{ 
              borderRadius: 8, 
              minHeight: 300,
              boxShadow: '0 4px 12px rgba(0,0,0,0.05)'
            }}
            bodyStyle={{ padding: 0 }}
          >
            <Tabs 
              activeKey={activeTab} 
              onChange={handleTabChange}
              style={{ padding: '0 24px' }}
            >
              <TabPane 
                tab={
                  <span>
                    <QuestionCircleOutlined />
                    即时问答
                  </span>
                } 
                key="analysis"
              >
                <div style={{ padding: '16px 24px' }}>
                  {loading ? (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200 }}>
                      <Spin tip="正在分析中..." size="large" />
                    </div>
                  ) : (
                    <div>
                      {result ? (
                        <div className="result-container">
                          <Divider orientation="left">
                            <ThunderboltOutlined style={{ color: '#52c41a' }} /> 投资分析
                          </Divider>
                          <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: 15, lineHeight: 1.8 }}>
                            {result}
                          </Paragraph>
                        </div>
                      ) : (
                        <div style={{ color: '#8c8c8c', textAlign: 'center', padding: '40px 0' }}>
                          <SearchOutlined style={{ fontSize: 40, color: '#d9d9d9', display: 'block', margin: '0 auto 20px' }} />
                          <p>分析结果将在这里显示</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </TabPane>

              <TabPane
                tab={
                  <span>
                    <FileOutlined />
                    报告列表
                  </span>
                }
                key="reports"
              >
                <div style={{ padding: '16px 24px' }}>
                  <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Title level={4}>历史分析报告</Title>
                    <Space>
                      <Button 
                        type="primary" 
                        icon={<SearchOutlined />}
                        onClick={loadReportsList}
                        loading={reportsLoading}
                      >
                        刷新列表
                      </Button>
                      <Button
                        onClick={() => {
                          fetch('/api/reports')
                            .then(response => response.json())
                            .then(data => {
                              console.log('报告列表API响应:', data);
                              message.info(`API响应: 找到${data.count || 0}个报告，目录: ${data.directory || '未知'}`);
                            })
                            .catch(error => {
                              console.error('API错误:', error);
                              message.error(`API错误: ${error.message}`);
                            });
                        }}
                      >
                        测试API
                      </Button>
                    </Space>
                  </div>
                  
                  <Table
                    columns={reportsColumns}
                    dataSource={allReports.map((item, index) => ({ ...item, key: index }))}
                    loading={reportsLoading}
                    pagination={{ pageSize: 5 }}
                    locale={{ emptyText: '暂无分析报告' }}
                  />
                </div>
              </TabPane>
            </Tabs>
          </Card>
        </div>
      </Content>
      <Footer style={{ textAlign: 'center', background: '#f0f2f5' }}>
        A股智能投顾系统 ©{new Date().getFullYear()} - 多智能体协同投资决策
      </Footer>
    </Layout>
  );
} 