import axios from 'axios';

// Base API configuration
export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
  // Enable sending secure cookies automatically
  withCredentials: true,
});

// Add request interceptor for potential CSRF handling or headers addition
apiClient.interceptors.request.use(
  (config) => {
    // If you are transitioning from localStorage, we can keep the local token fallback momentarily, 
    // or remove it completely to force HttpOnly cookie usage.
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

// Add response interceptor for global error handling
apiClient.interceptors.response.use(
  (response) => response.data, // Automatically extract data from response
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    
    // Handle auth errors globally (e.g., 401 Unauthorized)
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      // Clear legacy token just in case
      localStorage.removeItem('luvcraft_auth_token');
      // For HttpOnly cookies, the browser will ignore the server's clear cookie response if it's CORS lacking credentials, 
      // but assuming the backend clears the cookie on 401. 
      // Immediately invalidate the stale session by forcing window redirect to prevent further navigation.
      if (window.location.pathname !== '/login') {
        window.location.href = `/login?returnUrl=${encodeURIComponent(window.location.pathname)}`;
      }
    }
    
    // Handle rate-limiting globally (e.g. 429 Too Many Requests)
    if (error.response?.status === 429) {
      console.warn('Rate limit exceeded. Please slow down.');
      // Optional: dispatch an event to the global state to trigger a toast notification.
    }
    
    return Promise.reject(error.response?.data || { message: 'An unexpected error occurred' });
  }
);
