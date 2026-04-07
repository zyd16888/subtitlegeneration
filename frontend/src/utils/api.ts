/**
 * API 客户端
 * 自动处理认证 Token
 */

const API_BASE = ''; // 同源

/**
 * 获取认证 Token
 */
export function getToken(): string | null {
  return localStorage.getItem('token');
}

/**
 * 设置认证 Token
 */
export function setToken(token: string): void {
  localStorage.setItem('token', token);
}

/**
 * 清除认证 Token
 */
export function clearToken(): void {
  localStorage.removeItem('token');
}

/**
 * 获取认证头
 */
function getAuthHeaders(): HeadersInit {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * 检查是否已登录
 */
export function isLoggedIn(): boolean {
  return !!getToken();
}

/**
 * 通用 GET 请求
 */
export async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(error.detail || '请求失败');
  }
  return response.json();
}

/**
 * 通用 POST 请求
 */
export async function apiPost<T>(url: string, data?: any): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(error.detail || '请求失败');
  }
  return response.json();
}

/**
 * 通用 PUT 请求
 */
export async function apiPut<T>(url: string, data?: any): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(error.detail || '请求失败');
  }
  return response.json();
}

/**
 * 通用 DELETE 请求
 */
export async function apiDelete<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(error.detail || '请求失败');
  }
  return response.json();
}