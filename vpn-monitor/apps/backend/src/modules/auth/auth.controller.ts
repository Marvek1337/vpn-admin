import { Body, Controller, Get, Post, UseGuards } from '@nestjs/common';
import { LoginDto } from './dto/login.dto';
import { AuthService } from './auth.service';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { User } from '../../common/decorators/user.decorator';

@Controller('auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Post('login')
  login(@Body() dto: LoginDto) {
    return this.auth.login(dto.login, dto.password);
  }

  @UseGuards(JwtAuthGuard)
  @Get('me')
  me(@User() user: { id: string }) {
    return this.auth.me(user.id);
  }
}
