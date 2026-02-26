import { IsInt, IsString } from 'class-validator';

export class TestSshDto {
  @IsString() host: string;
  @IsInt() sshPort: number;
  @IsString() sshUsername: string;
  @IsString() sshPassword: string;
}
