import { IsOptional, IsString } from 'class-validator';

export class CreateClientDto {
  @IsString() name: string;
  @IsOptional() @IsString() address?: string;
}
