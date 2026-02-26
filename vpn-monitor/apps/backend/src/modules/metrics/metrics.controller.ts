import { Controller, Get, Param, Query, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { MetricsService } from './metrics.service';
import { MetricsQueryDto } from './dto/metrics-query.dto';

@UseGuards(JwtAuthGuard)
@Controller('servers/:id/metrics')
export class MetricsController {
  constructor(private readonly metrics: MetricsService) {}

  @Get()
  list(@Param('id') id: string, @Query() q: MetricsQueryDto) {
    return this.metrics.forServer(id, q.range, q.step);
  }
}
