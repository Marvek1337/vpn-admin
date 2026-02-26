import { Injectable } from '@nestjs/common';
import * as crypto from 'crypto';

@Injectable()
export class CryptoService {
  private readonly key = crypto.createHash('sha256').update(process.env.APP_SECRET_KEY || 'change_me_32bytes').digest();

  encrypt(plaintext: string): string {
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', this.key, iv);
    const encrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    return Buffer.from(JSON.stringify({ iv: iv.toString('base64'), tag: tag.toString('base64'), ciphertext: encrypted.toString('base64') })).toString('base64');
  }

  decrypt(stored: string): string {
    const raw = JSON.parse(Buffer.from(stored, 'base64').toString('utf8'));
    const decipher = crypto.createDecipheriv('aes-256-gcm', this.key, Buffer.from(raw.iv, 'base64'));
    decipher.setAuthTag(Buffer.from(raw.tag, 'base64'));
    return Buffer.concat([decipher.update(Buffer.from(raw.ciphertext, 'base64')), decipher.final()]).toString('utf8');
  }
}
