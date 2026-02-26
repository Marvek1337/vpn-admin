import { IsString } from 'class-validator';

export class TestWgDto {
  @IsString() wgEasyUrl: string;
  @IsString() wgEasyUsername: string;
  @IsString() wgEasyPassword: string;
}
