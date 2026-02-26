import { Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcryptjs';
import { UsersService } from '../users/users.service';

@Injectable()
export class AuthService {
  constructor(private readonly users: UsersService, private readonly jwt: JwtService) {}

  async login(login: string, password: string) {
    const user = await this.users.findByLogin(login);
    if (!user || !(await bcrypt.compare(password, user.passwordHash))) {
      throw new UnauthorizedException('Invalid credentials');
    }
    const userPayload = { id: user.id, login: user.login, role: user.role };
    return { accessToken: this.jwt.sign(userPayload), user: userPayload };
  }

  async me(userId: string) {
    const user = await this.users.findById(userId);
    return user ? { id: user.id, login: user.login, role: user.role } : null;
  }
}
