import { registerAs } from '@nestjs/config';

export default registerAs('app', () => {
  const rawPort = process.env.PORT ?? '3102';
  const port = Number.parseInt(rawPort, 10);
  if (!Number.isFinite(port) || port < 1 || port > 65535) {
    throw new Error(`Invalid PORT: '${rawPort}'. Must be an integer between 1 and 65535.`);
  }

  return {
    port,
    nodeEnv: process.env.NODE_ENV ?? 'development',
  };
});
