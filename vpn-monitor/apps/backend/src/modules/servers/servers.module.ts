import { Module } from '@nestjs/common';
import { ServersController } from './servers.controller';
import { ServersService } from './servers.service';
import { PrismaService } from '../../common/prisma.service';
import { CryptoModule } from '../crypto/crypto.module';
import { SshService } from '../ssh/ssh.service';
import { WgModule } from '../wg/wg.module';

@Module({ imports: [CryptoModule, WgModule], controllers: [ServersController], providers: [ServersService, PrismaService, SshService], exports: [ServersService] })
export class ServersModule {}
