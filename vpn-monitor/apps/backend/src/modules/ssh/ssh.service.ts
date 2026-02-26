import { Injectable } from '@nestjs/common';
import { NodeSSH } from 'node-ssh';
import { parseFree } from './ssh.parsers';

@Injectable()
export class SshService {
  private readonly netState = new Map<string, { rx: number; tx: number; ts: number }>();

  async test(host: string, port: number, username: string, password: string) {
    const ssh = new NodeSSH();
    const start = Date.now();
    await ssh.connect({ host, port, username, password, readyTimeout: 8000 });
    ssh.dispose();
    return { ok: true, latencyMs: Date.now() - start };
  }

  async collect(serverId: string, host: string, port: number, username: string, password: string) {
    const ssh = new NodeSSH();
    await ssh.connect({ host, port, username, password, readyTimeout: 10000 });
    const [free, disk, loadavg, uptime, stat1, net1] = await Promise.all([
      ssh.execCommand('free -b'),
      ssh.execCommand('df -B1 / | tail -1'),
      ssh.execCommand('cat /proc/loadavg'),
      ssh.execCommand('cat /proc/uptime'),
      ssh.execCommand('cat /proc/stat | head -1'),
      ssh.execCommand('cat /proc/net/dev'),
    ]);
    await new Promise((r) => setTimeout(r, 300));
    const stat2 = await ssh.execCommand('cat /proc/stat | head -1');
    ssh.dispose();

    const mem = parseFree(free.stdout);
    const diskParts = disk.stdout.trim().split(/\s+/);
    const loads = loadavg.stdout.trim().split(/\s+/);
    const up = Number((uptime.stdout || '0').split(' ')[0]);

    const cpuA = stat1.stdout.trim().split(/\s+/).slice(1).map(Number);
    const cpuB = stat2.stdout.trim().split(/\s+/).slice(1).map(Number);
    const idleA = cpuA[3] + (cpuA[4] || 0);
    const idleB = cpuB[3] + (cpuB[4] || 0);
    const totalA = cpuA.reduce((a, b) => a + b, 0);
    const totalB = cpuB.reduce((a, b) => a + b, 0);
    const cpuPercent = (1 - (idleB - idleA) / (totalB - totalA || 1)) * 100;

    const ifaceLine = (net1.stdout.split('\n').find((l) => l.includes(':') && !l.includes('lo:')) || '').replace(':', ' ').trim().split(/\s+/);
    const rx = Number(ifaceLine[1] || 0);
    const tx = Number(ifaceLine[9] || 0);
    const now = Date.now();
    const prev = this.netState.get(serverId);
    const netRxBps = prev ? ((rx - prev.rx) * 1000) / Math.max(now - prev.ts, 1) : 0;
    const netTxBps = prev ? ((tx - prev.tx) * 1000) / Math.max(now - prev.ts, 1) : 0;
    this.netState.set(serverId, { rx, tx, ts: now });

    return {
      cpuPercent,
      ramUsedBytes: mem.used,
      ramTotalBytes: mem.total,
      diskUsedBytes: Number(diskParts[2] || 0),
      diskTotalBytes: Number(diskParts[1] || 0),
      netRxBps,
      netTxBps,
      load1: Number(loads[0] || 0),
      load5: Number(loads[1] || 0),
      load15: Number(loads[2] || 0),
      uptimeSec: up,
    };
  }
}
