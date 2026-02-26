import { Injectable } from '@nestjs/common';
import { Interval } from '@nestjs/schedule';
import { PrismaService } from '../../common/prisma.service';
import { ServersService } from '../servers/servers.service';
import { SshService } from '../ssh/ssh.service';
import { WgService } from '../wg/wg.service';
import { MetricsService } from './metrics.service';

@Injectable()
export class MetricsPoller {
  private lastMetrics = new Map<string, number>();
  private lastWg = new Map<string, number>();

  constructor(private prisma: PrismaService, private servers: ServersService, private ssh: SshService, private wg: WgService, private metricsService: MetricsService) {}

  @Interval(5000)
  async tick() {
    const servers = await this.prisma.server.findMany();
    const now = Date.now();

    for (const s of servers) {
      if (now - (this.lastMetrics.get(s.id) || 0) >= s.metricsPollIntervalSec * 1000) {
        try {
          const creds = await this.servers.credentials(s.id);
          const metric = await this.ssh.collect(s.id, s.host, s.sshPort, s.sshUsername, creds.sshPassword);
          await this.prisma.serverMetric.create({ data: { serverId: s.id, ...metric } as any });
          await this.prisma.server.update({ where: { id: s.id }, data: { lastSshOk: true, lastMetricsAt: new Date(), lastErrorMessage: null } });
        } catch (e: any) {
          await this.prisma.server.update({ where: { id: s.id }, data: { lastSshOk: false, lastErrorMessage: e.message } });
        }
        this.lastMetrics.set(s.id, now);
      }

      if (now - (this.lastWg.get(s.id) || 0) >= s.wgPollIntervalSec * 1000) {
        try {
          await this.wg.listClients(s.id);
          await this.prisma.server.update({ where: { id: s.id }, data: { lastWgOk: true, lastWgSyncAt: new Date(), lastErrorMessage: null } });
        } catch (e: any) {
          await this.prisma.server.update({ where: { id: s.id }, data: { lastWgOk: false, lastErrorMessage: e.message } });
        }
        this.lastWg.set(s.id, now);
      }
    }
  }

  @Interval(3600000)
  prune() {
    return this.metricsService.retention();
  }
}
