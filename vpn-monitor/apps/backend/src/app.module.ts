import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';
import { AuthModule } from './modules/auth/auth.module';
import { UsersModule } from './modules/users/users.module';
import { ServersModule } from './modules/servers/servers.module';
import { MetricsModule } from './modules/metrics/metrics.module';
import { WgModule } from './modules/wg/wg.module';
import { CryptoModule } from './modules/crypto/crypto.module';
import { HealthController } from './modules/health/health.controller';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), ScheduleModule.forRoot(), AuthModule, UsersModule, ServersModule, MetricsModule, WgModule, CryptoModule],
  controllers: [HealthController],
})
export class AppModule {}
