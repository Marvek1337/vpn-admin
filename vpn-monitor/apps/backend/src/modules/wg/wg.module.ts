import { Module } from '@nestjs/common';
import { WgController } from './wg.controller';
import { WgService } from './wg.service';
import { PrismaService } from '../../common/prisma.service';
import { CryptoModule } from '../crypto/crypto.module';

@Module({ imports: [CryptoModule], controllers: [WgController], providers: [WgService, PrismaService], exports: [WgService] })
export class WgModule {}
