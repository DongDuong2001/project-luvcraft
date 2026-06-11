import axios from 'axios';

const apiRoot = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export const apiClient = axios.create({
  baseURL: `${apiRoot}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

apiClient.interceptors.request.use(
  (config) => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('luvcraft_auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('luvcraft_auth_token');
      if (window.location.pathname !== '/login') {
        window.location.href = `/login?returnUrl=${encodeURIComponent(window.location.pathname)}`;
      }
    }
    
    if (error.response?.status === 429) {
      console.warn('Rate limit exceeded. Please slow down.');
    }
    
    return Promise.reject(error);
  }
);

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as
      | { detail?: string | Array<{ msg?: string }>; message?: string }
      | undefined;

    if (typeof payload?.detail === 'string') {
      return payload.detail;
    }
    if (Array.isArray(payload?.detail)) {
      return payload.detail.map((item) => item.msg).filter(Boolean).join(', ') || 'Invalid request';
    }
    if (payload?.message) {
      return payload.message;
    }
    if (!error.response) {
      return 'Cannot connect to the backend API';
    }
    return `Backend request failed (${error.response.status})`;
  }

  return error instanceof Error ? error.message : 'An unexpected error occurred';
}
