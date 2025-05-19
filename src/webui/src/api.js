import axios from 'axios';

/**
 * 发送分析请求到后端
 * @param {string} query 用户输入的自然语言分析请求
 * @returns {Promise<string>} 分析结果
 */
export async function askAgent(query) {
  const resp = await axios.post('/api/ask', { query });
  return resp.data.result || JSON.stringify(resp.data);
}

/**
 * 获取股票分析报告内容
 * @param {string} ticker 股票代码
 * @returns {Promise<{content: string, filename: string, ticker: string}>} 报告内容和元数据
 */
export async function getStockReport(ticker) {
  try {
    console.log(`尝试获取股票${ticker}的报告...`);
    const resp = await axios.get(`/api/report/${ticker}`);
    console.log(`成功获取股票${ticker}的报告:`, resp.data);
    return resp.data;
  } catch (error) {
    console.error('获取报告失败:', error);
    // 提供更详细的错误信息
    if (error.response) {
      console.error('错误响应:', error.response.data);
      throw new Error(`服务器错误(${error.response.status}): ${error.response.data.detail || '未知错误'}`);
    } else if (error.request) {
      throw new Error('未收到服务器响应，请检查后端服务是否启动');
    } else {
      throw error;
    }
  }
}

/**
 * 获取可用的分析报告列表
 * @returns {Promise<Array>} 报告列表
 */
export async function getReportsList() {
  try {
    const resp = await axios.get('/api/reports');
    return resp.data.reports;
  } catch (error) {
    console.error('获取报告列表失败:', error);
    return [];
  }
}

/**
 * 获取报告下载链接
 * @param {string} ticker 股票代码
 * @returns {string} 下载链接
 */
export function getReportDownloadUrl(ticker) {
  return `/api/report/${ticker}/download`;
} 