import axios from 'axios';

export const http = axios.create({ baseURL: `${import.meta.env.VITE_API_BASE_URL || ''}/api` });

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response?.status === 401) {
      localStorage.removeItem('accessToken');
      window.location.href = '/login';
    }
    return Promise.reject(e);
  },
);
