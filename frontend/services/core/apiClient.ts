const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

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
          // Clear client-side login flag
          localStorage.removeItem('luvcraft_logged_in');
          if (window.location.pathname !== '/login') {
            window.location.href = `/login?returnUrl=${encodeURIComponent(window.location.pathname)}`;
          }
        }
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed with status ${response.status}`);
      }

      return await response.json() as T;
    } catch (error) {
      console.error('API Client Error:', error);
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
