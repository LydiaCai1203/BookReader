// API 配置
// 前后端部署在同一服务器，后端端口 8000

const getApiBase = () => {
  // 自动使用当前页面的 hostname，后端端口为 8000
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8000`;
};

export const API_BASE = getApiBase();
export const API_URL = `${API_BASE}/api`;
