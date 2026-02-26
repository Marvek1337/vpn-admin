import { defineStore } from 'pinia';
import { http } from '../api/http';

export const useMetricsStore = defineStore('metrics', {
  state: () => ({ series: [] as any[] }),
  actions: {
    async fetch(serverId: string, range = '1h', step = '30s') {
      const { data } = await http.get(`/servers/${serverId}/metrics`, { params: { range, step } });
      this.series = data.series;
    },
  },
});
