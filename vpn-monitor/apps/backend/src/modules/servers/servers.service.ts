import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../common/prisma.service';
import { CryptoService } from '../crypto/crypto.service';
import { CreateServerDto } from './dto/create-server.dto';
import { UpdateServerDto } from './dto/update-server.dto';
import { SshService } from '../ssh/ssh.service';
import { WgService } from '../wg/wg.service';

@Injectable()
export class ServersService {
  constructor(private prisma: PrismaService, private crypto: CryptoService, private ssh: SshService, private wg: WgService) {}

  private sanitize(server: any) {
    const { sshPasswordEnc, wgEasyPasswordEnc, ...safe } = server;
    return safe;
  }

  async findAll() {
    const rows = await this.prisma.server.findMany({ include: { metrics: { orderBy: { ts: 'desc' }, take: 1 } } });
    return rows.map((x) => ({ ...this.sanitize(x), latestMetric: x.metrics[0] || null, metrics: undefined }));
  }

  async findOne(id: string) {
    const server = await this.prisma.server.findUnique({ where: { id }, include: { metrics: { orderBy: { ts: 'desc' }, take: 1 } } });
    if (!server) throw new NotFoundException('Server not found');
    return { ...this.sanitize(server), latestMetric: server.metrics[0] || null, metrics: undefined };
  }

  create(dto: CreateServerDto) {
    return this.prisma.server.create({ data: { ...dto, sshPasswordEnc: this.crypto.encrypt(dto.sshPassword), wgEasyPasswordEnc: this.crypto.encrypt(dto.wgEasyPassword) } }).then((s) => this.sanitize(s));
  }

  async update(id: string, dto: UpdateServerDto) {
    const data: any = { ...dto };
    if (dto.sshPassword) data.sshPasswordEnc = this.crypto.encrypt(dto.sshPassword);
    if (dto.wgEasyPassword) data.wgEasyPasswordEnc = this.crypto.encrypt(dto.wgEasyPassword);
    delete data.sshPassword;
    delete data.wgEasyPassword;
    const updated = await this.prisma.server.update({ where: { id }, data });
    return this.sanitize(updated);
  }

  remove(id: string) {
    return this.prisma.server.delete({ where: { id } });
  }

  testSsh(dto: any) {
    return this.ssh.test(dto.host, dto.sshPort, dto.sshUsername, dto.sshPassword);
  }

  async testWg(dto: any) {
    await this.wg.test(dto.wgEasyUrl, dto.wgEasyUsername, dto.wgEasyPassword);
    return { ok: true };
  }

  async credentials(serverId: string) {
    const s = await this.prisma.server.findUnique({ where: { id: serverId } });
    if (!s) throw new NotFoundException('Server not found');
    return {
      ...s,
      sshPassword: this.crypto.decrypt(s.sshPasswordEnc),
      wgEasyPassword: this.crypto.decrypt(s.wgEasyPasswordEnc),
    };
  }
}
