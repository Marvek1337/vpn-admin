import { Injectable } from '@nestjs/common';
import { PrismaService } from '../../common/prisma.service';

@Injectable()
export class MetricsService {
  constructor(private prisma: PrismaService) {}

  async forServer(serverId: string, range: string, step: string) {
    const map: Record<string, number> = { '1h': 3600, '6h': 21600, '24h': 86400, '7d': 604800 };
    const since = new Date(Date.now() - (map[range] || 3600) * 1000);
    const series = await this.prisma.serverMetric.findMany({ where: { serverId, ts: { gte: since } }, orderBy: { ts: 'asc' } });
    return { serverId, range, step, series };
  }

  retention() {
    const since = new Date(Date.now() - 7 * 24 * 3600 * 1000);
    return this.prisma.serverMetric.deleteMany({ where: { ts: { lt: since } } });
  }
}
