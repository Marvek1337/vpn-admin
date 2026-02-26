import { defineStore } from 'pinia';
import { http } from '../api/http';

export const useServersStore = defineStore('servers', {
  state: () => ({ items: [] as any[] }),
  actions: {
    async fetchAll() {
      const { data } = await http.get('/servers');
      this.items = data;
    },
  },
});
