import { createParamDecorator, ExecutionContext } from '@nestjs/common';

export const User = createParamDecorator((_: unknown, ctx: ExecutionContext) => ctx.switchToHttp().getRequest().user);
