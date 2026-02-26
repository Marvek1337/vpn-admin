import { IsOptional, IsString } from 'class-validator';

export class MetricsQueryDto {
  @IsOptional() @IsString() range = '1h';
  @IsOptional() @IsString() step = '30s';
}
