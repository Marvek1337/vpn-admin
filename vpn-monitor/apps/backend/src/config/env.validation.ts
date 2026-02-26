import { IsString } from 'class-validator';

export class EnvValidation {
  @IsString()
  DATABASE_URL: string;
}
