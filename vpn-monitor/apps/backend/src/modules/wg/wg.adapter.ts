import axios, { AxiosInstance } from 'axios';

export class WgAdapter {
  private clients = new Map<string, AxiosInstance>();

  private api(serverId: string, baseUrl: string) {
    if (!this.clients.has(serverId)) {
      this.clients.set(serverId, axios.create({ baseURL: baseUrl, timeout: 10000, withCredentials: true }));
    }
    return this.clients.get(serverId)!;
  }

  async login(serverId: string, baseUrl: string, username: string, password: string) {
    const api = this.api(serverId, baseUrl);
    await api.post('/api/session', { password, username });
  }

  async request(serverId: string, baseUrl: string, creds: { username: string; password: string }, method: 'get'|'post'|'put'|'delete', path: string, data?: any) {
    const api = this.api(serverId, baseUrl);
    try {
      return await api.request({ method, url: path, data });
    } catch (e: any) {
      if (e.response?.status === 401) {
        await this.login(serverId, baseUrl, creds.username, creds.password);
        return api.request({ method, url: path, data });
      }
      throw e;
    }
  }
}
