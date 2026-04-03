import { describe, expect, it } from 'vitest';
import { HealthController } from './health.controller';

describe('HealthController', () => {
  it('should return ok status', () => {
    const controller = new HealthController({ ping: async () => ({}) } as never);
    const result = controller.check();
    expect(result.status).toBe('ok');
    expect(result.timestamp).toBeDefined();
  });

  it('should report ready when opensearch ping succeeds', async () => {
    const controller = new HealthController({ ping: async () => ({}) } as never);
    const result = await controller.ready();
    expect(result.status).toBe('ok');
    expect(result.checks.opensearch.status).toBe('ok');
  });

  it('should report degraded when opensearch ping fails', async () => {
    const controller = new HealthController({
      ping: async () => {
        throw new Error('connection failed');
      },
    } as never);
    const result = await controller.ready();
    expect(result.status).toBe('degraded');
    expect(result.checks.opensearch.status).toBe('error');
  });
});
