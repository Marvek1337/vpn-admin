import { defineStore } from 'pinia';
import { http } from '../api/http';

export const useWgClientsStore = defineStore('wgClients', {
  state: () => ({ clients: [] as any[] }),
  actions: {
    async fetch(serverId: string) {
      const { data } = await http.get(`/servers/${serverId}/wg/clients`);
      this.clients = data.clients;
    },
  },
});
