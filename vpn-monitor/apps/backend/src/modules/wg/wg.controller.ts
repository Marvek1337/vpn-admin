import { Body, Controller, Delete, Get, Param, Post, Put, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { WgService } from './wg.service';
import { CreateClientDto } from './dto/create-client.dto';
import { UpdateClientDto } from './dto/update-client.dto';

@UseGuards(JwtAuthGuard)
@Controller('servers/:id/wg/clients')
export class WgController {
  constructor(private readonly wg: WgService) {}

  @Get() list(@Param('id') id: string) { return this.wg.listClients(id); }
  @Post() create(@Param('id') id: string, @Body() dto: CreateClientDto) { return this.wg.createClient(id, dto); }
  @Put(':clientId') update(@Param('id') id: string, @Param('clientId') clientId: string, @Body() dto: UpdateClientDto) { return this.wg.updateClient(id, clientId, dto); }
  @Post(':clientId/enable') enable(@Param('id') id: string, @Param('clientId') clientId: string) { return this.wg.enable(id, clientId, true); }
  @Post(':clientId/disable') disable(@Param('id') id: string, @Param('clientId') clientId: string) { return this.wg.enable(id, clientId, false); }
  @Delete(':clientId') remove(@Param('id') id: string, @Param('clientId') clientId: string) { return this.wg.deleteClient(id, clientId); }
}
