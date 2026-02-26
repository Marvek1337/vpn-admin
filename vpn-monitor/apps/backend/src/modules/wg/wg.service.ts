import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../common/prisma.service';
import { CryptoService } from '../crypto/crypto.service';
import { WgAdapter } from './wg.adapter';

@Injectable()
export class WgService {
  private adapter = new WgAdapter();

  constructor(private prisma: PrismaService, private crypto: CryptoService) {}

  private async server(id: string) {
    const s = await this.prisma.server.findUnique({ where: { id } });
    if (!s) throw new NotFoundException('Server not found');
    return { ...s, wgEasyPassword: this.crypto.decrypt(s.wgEasyPasswordEnc) };
  }

  async test(baseUrl: string, username: string, password: string) {
    await this.adapter.login('test', baseUrl, username, password);
  }

  async listClients(serverId: string) {
    const s = await this.server(serverId);
    const res = await this.adapter.request(serverId, s.wgEasyUrl, { username: s.wgEasyUsername, password: s.wgEasyPassword }, 'get', '/api/wireguard/client');
    const clients = res.data || [];
    return { serverId, clients, summary: { total: clients.length, enabled: clients.filter((c: any) => c.enabled).length, active: clients.filter((c: any) => c.latestHandshakeAt).length } };
  }

  createClient(serverId: string, dto: any) {
    return this.server(serverId).then((s) => this.adapter.request(serverId, s.wgEasyUrl, { username: s.wgEasyUsername, password: s.wgEasyPassword }, 'post', '/api/wireguard/client', dto).then((r) => r.data));
  }

  updateClient(serverId: string, clientId: string, dto: any) {
    return this.server(serverId).then((s) => this.adapter.request(serverId, s.wgEasyUrl, { username: s.wgEasyUsername, password: s.wgEasyPassword }, 'put', `/api/wireguard/client/${clientId}`, dto).then((r) => r.data));
  }

  deleteClient(serverId: string, clientId: string) {
    return this.server(serverId).then((s) => this.adapter.request(serverId, s.wgEasyUrl, { username: s.wgEasyUsername, password: s.wgEasyPassword }, 'delete', `/api/wireguard/client/${clientId}`).then(() => ({ ok: true })));
  }

  enable(serverId: string, clientId: string, enabled: boolean) {
    return this.server(serverId).then((s) => this.adapter.request(serverId, s.wgEasyUrl, { username: s.wgEasyUsername, password: s.wgEasyPassword }, 'post', `/api/wireguard/client/${clientId}/${enabled ? 'enable' : 'disable'}`).then((r) => r.data));
  }
}
