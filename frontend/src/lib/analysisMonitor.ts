import type { AnalysisJob } from '../api';

export function waitForPoll(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}

export async function retryRead<T>(read: () => Promise<T>, signal: AbortSignal,
  onConnection: (retrying: boolean) => void, wait = waitForPoll): Promise<T> {
  let failures = 0;
  for (;;) {
    signal.throwIfAborted();
    try {
      const result = await read();
      signal.throwIfAborted();
      onConnection(false);
      return result;
    } catch (error) {
      signal.throwIfAborted();
      const status = (error as { status?: number })?.status;
      if (status && status !== 408 && status !== 429 && status < 500) throw error;
      onConnection(true);
      await wait(Math.min(1500 * 2 ** Math.min(failures++, 4), 15000), signal);
    }
  }
}

export async function monitorAnalysis<T>(initial: AnalysisJob, options: {
  signal: AbortSignal;
  readJob: () => Promise<AnalysisJob>;
  readResult: () => Promise<T>;
  onJob: (job: AnalysisJob) => void;
  onConnection: (retrying: boolean) => void;
  wait?: typeof waitForPoll;
}): Promise<T> {
  const { signal, onJob, onConnection, readJob, readResult, wait = waitForPoll } = options;
  let job = initial;
  for (;;) {
    signal.throwIfAborted();
    onJob(job);
    if (job.status === 'failed') throw new Error(job.error || 'Proses analisis gagal');
    if (job.status === 'completed') return retryRead(readResult, signal, onConnection, wait);
    await wait(1500, signal);
    job = await retryRead(readJob, signal, onConnection, wait);
  }
}
