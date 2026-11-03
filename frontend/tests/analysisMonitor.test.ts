import { test } from 'node:test';
import assert from 'node:assert/strict';
import { monitorAnalysis, retryRead, waitForPoll } from '../src/lib/analysisMonitor.ts';
import type { AnalysisJob } from '../src/api.ts';
const job = (status: AnalysisJob['status'], progress = 0): AnalysisJob => ({
  id: 'existing-job', status, progress, message: status, error: null,
});
const noWait = async () => {};

test('recovered job resumes from its current progress and retrieves its result', async () => {
  const updates: number[] = [];
  const jobs = [job('running', 80), job('completed', 100)];
  const result = await monitorAnalysis(job('running', 47), {
    signal: new AbortController().signal, wait: noWait,
    readJob: async () => jobs.shift()!, readResult: async () => ({ job_id: 'existing-job' }),
    onJob: next => updates.push(next.progress), onConnection: () => {},
  });
  assert.deepEqual(updates, [47, 80, 100]);
  assert.equal(result.job_id, 'existing-job');
});

test('connection interruptions and server errors retry reads without losing progress', async () => {
  let polls = 0, results = 0;
  const progress: number[] = [], retries: boolean[] = [], delays: number[] = [];
  await monitorAnalysis(job('queued'), {
    signal: new AbortController().signal, wait: async ms => { delays.push(ms); },
    readJob: async () => {
      polls++;
      if (polls === 1) throw new TypeError('Failed to fetch');
      if (polls === 2) throw Object.assign(new Error('Unavailable'), { status: 503 });
      return job('completed', 100);
    },
    readResult: async () => {
      if (++results === 1) throw new DOMException('Timeout', 'AbortError');
      return 'done';
    },
    onJob: next => progress.push(next.progress), onConnection: retry => retries.push(retry),
  });
  assert.equal(polls, 3);
  assert.equal(results, 2);
  assert.deepEqual(progress, [0, 100]);
  assert.ok(delays.includes(3000));
  assert.deepEqual(retries, [true, true, false, true, false]);
});

test('a job completed while the page was closed retrieves results immediately', async () => {
  const result = await monitorAnalysis(job('completed', 100), {
    signal: new AbortController().signal,
    readJob: async () => { throw Error('Should not poll'); },
    readResult: async () => 'completed result', onJob: () => {}, onConnection: () => {},
  });
  assert.equal(result, 'completed result');
});

test('failed jobs show their failure instead of retrying or loading old results', async () => {
  await assert.rejects(monitorAnalysis({ ...job('failed'), error: 'Server restarted' }, {
    signal: new AbortController().signal,
    readJob: async () => { throw Error('Unexpected poll'); },
    readResult: async () => { throw Error('Unexpected result'); },
    onJob: () => {}, onConnection: () => {},
  }), /Server restarted/);
});

test('permission and missing-resource errors stop retrying', async () => {
  for (const status of [401, 403, 404]) {
    let reads = 0;
    await assert.rejects(retryRead(async () => {
      reads++; throw Object.assign(new Error('Denied'), { status });
    }, new AbortController().signal, () => {}, noWait), /Denied/);
    assert.equal(reads, 1);
  }
});

test('unmount/refresh aborts old polling and prevents stale updates', async () => {
  const controller = new AbortController();
  let updates = 0;
  await assert.rejects(monitorAnalysis(job('running', 47), {
    signal: controller.signal, wait: noWait,
    readJob: async () => { controller.abort(); return job('completed', 100); },
    readResult: async () => { throw Error('Unexpected result'); },
    onJob: () => { updates++; }, onConnection: () => {},
  }), { name: 'AbortError' });
  assert.equal(updates, 1);
  const waiting = new AbortController();
  const promise = waitForPoll(15000, waiting.signal);
  waiting.abort();
  await assert.rejects(promise, { name: 'AbortError' });
});
