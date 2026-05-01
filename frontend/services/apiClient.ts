import axios from 'axios';

// Base API configuration
export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for authentication
apiClient.interceptors.request.use(
  (config) => {
    // Check if we are running in browser environment before trying to access localStorage
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
      // Clear token and potentially redirect to login
      localStorage.removeItem('luvcraft_auth_token');
      // window.location.href = '/login'; 
    }
    
    return Promise.reject(error.response?.data || { message: 'An unexpected error occurred' });
  }
);
