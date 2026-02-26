import { Injectable } from '@nestjs/common';
import { PrismaService } from '../../common/prisma.service';

@Injectable()
export class UsersService {
  constructor(private readonly prisma: PrismaService) {}

  findByLogin(login: string) {
    return this.prisma.user.findUnique({ where: { login } });
  }

  findById(id: string) {
    return this.prisma.user.findUnique({ where: { id } });
  }
}
