import { defineStore } from 'pinia';
import { http } from '../api/http';

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null as any, accessToken: localStorage.getItem('accessToken') || '' }),
  actions: {
    async login(login: string, password: string) {
      const { data } = await http.post('/auth/login', { login, password });
      this.accessToken = data.accessToken;
      this.user = data.user;
      localStorage.setItem('accessToken', data.accessToken);
    },
    logout() {
      this.accessToken = '';
      this.user = null;
      localStorage.removeItem('accessToken');
    },
  },
});
