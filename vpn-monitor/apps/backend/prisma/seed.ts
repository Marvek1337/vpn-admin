import { PrismaClient, Role } from '@prisma/client';
import * as bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function main() {
  const login = process.env.ADMIN_LOGIN || 'admin';
  const password = process.env.ADMIN_PASSWORD || 'admin';
  const existing = await prisma.user.findUnique({ where: { login } });
  if (!existing) {
    await prisma.user.create({
      data: {
        login,
        passwordHash: await bcrypt.hash(password, 10),
        role: Role.ADMIN,
      },
    });
  }
}

main().finally(() => prisma.$disconnect());
