import { Module, forwardRef } from '@nestjs/common';
import { MetricsController } from './metrics.controller';
import { MetricsService } from './metrics.service';
import { MetricsPoller } from './metrics.poller';
import { PrismaService } from '../../common/prisma.service';
import { ServersModule } from '../servers/servers.module';
import { SshService } from '../ssh/ssh.service';
import { WgModule } from '../wg/wg.module';

@Module({ imports: [forwardRef(() => ServersModule), WgModule], controllers: [MetricsController], providers: [MetricsService, MetricsPoller, PrismaService, SshService], exports: [MetricsService] })
export class MetricsModule {}
