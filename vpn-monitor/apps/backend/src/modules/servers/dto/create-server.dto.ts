import { IsInt, IsOptional, IsString, Min } from 'class-validator';

export class CreateServerDto {
  @IsString() name: string;
  @IsOptional() @IsString() description?: string;
  @IsString() host: string;
  @IsInt() sshPort: number;
  @IsString() sshUsername: string;
  @IsString() sshPassword: string;
  @IsString() wgEasyUrl: string;
  @IsString() wgEasyUsername: string;
  @IsString() wgEasyPassword: string;
  @IsOptional() @IsInt() @Min(5) metricsPollIntervalSec?: number;
  @IsOptional() @IsInt() @Min(10) wgPollIntervalSec?: number;
}
