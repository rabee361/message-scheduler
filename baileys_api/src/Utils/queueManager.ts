import PQueue from 'p-queue';

const sessionQueues: Map<string, PQueue> = new Map();

export function getSessionQueue(sessionId: string): PQueue {
  if (!sessionQueues.has(sessionId)) {
    const queue = new PQueue({
      concurrency: 1,       // Only one task at a time per session
      interval: 10000,       // Optional: 10 seconds between tasks
      intervalCap: 1        // Optional: 1 task per interval
    });
    sessionQueues.set(sessionId, queue);
  }
  return sessionQueues.get(sessionId)!;
}
