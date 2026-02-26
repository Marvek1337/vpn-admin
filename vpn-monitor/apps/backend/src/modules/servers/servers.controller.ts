import { Body, Controller, Delete, Get, Param, Post, Put, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { ServersService } from './servers.service';
import { CreateServerDto } from './dto/create-server.dto';
import { UpdateServerDto } from './dto/update-server.dto';
import { TestSshDto } from './dto/test-ssh.dto';
import { TestWgDto } from './dto/test-wg.dto';

@UseGuards(JwtAuthGuard)
@Controller('servers')
export class ServersController {
  constructor(private readonly servers: ServersService) {}

  @Get() findAll() { return this.servers.findAll(); }
  @Get(':id') findOne(@Param('id') id: string) { return this.servers.findOne(id); }
  @Post() create(@Body() dto: CreateServerDto) { return this.servers.create(dto); }
  @Put(':id') update(@Param('id') id: string, @Body() dto: UpdateServerDto) { return this.servers.update(id, dto); }
  @Delete(':id') delete(@Param('id') id: string) { return this.servers.remove(id); }
  @Post('test-ssh') testSsh(@Body() dto: TestSshDto) { return this.servers.testSsh(dto); }
  @Post('test-wg') testWg(@Body() dto: TestWgDto) { return this.servers.testWg(dto); }
}
