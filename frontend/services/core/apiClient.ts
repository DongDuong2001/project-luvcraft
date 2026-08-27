const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorMessage(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => typeof item === 'object' && item !== null && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : null)
        .filter(Boolean);
      if (messages.length > 0) return messages.join('; ');
    }
  }
  return `Request failed with status ${status}`;
}

export const apiClient = {
  /**
   * Safe native wrapper for HTTP requests replacing Axios
   */
  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${API_BASE_URL}/api/v1${endpoint}`;

    // Standard headers
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const config: RequestInit = {
      ...options,
      headers,
      // CRITICAL: Tells the browser to automatically include HTTPOnly Cookies
      credentials: 'include', 
    };

    try {
      const response = await fetch(url, config);

      // Handle 401 Unauthorized (Session Expired)
      if (response.status === 401) {
        if (typeof window !== 'undefined') {
          if (window.location.pathname !== '/login') {
            // Preserve the query string so filters/params survive re-authentication.
            const returnUrl = `${window.location.pathname}${window.location.search}`;
            window.location.href = `/login?returnUrl=${encodeURIComponent(returnUrl)}`;
          }
        }
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        const errorData: unknown = await response.json().catch(() => null);
        throw new ApiError(errorMessage(errorData, response.status), response.status, errorData);
      }

      if (response.status === 204) return undefined as T;
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new ApiError('The server returned an unexpected response format', response.status);
      }
      return await response.json() as T;
    } catch (error) {
      // Request cancellation is expected when a component unmounts or a newer
      // request supersedes an older one. Logging it as an error makes the
      // Next.js development overlay report a false runtime failure.
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        console.error('API Client Error:', error);
      }
      throw error;
    }
  },

  // HTTP Helper shortcuts
  async get<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  },

  async post<T>(endpoint: string, data: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async put<T>(endpoint: string, data: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async patch<T>(endpoint: string, data: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  async delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
};

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}
