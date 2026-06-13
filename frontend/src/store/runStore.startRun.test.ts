// Tests for runStore.startRun — mocks streamBrief via vi.mock.

import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { Mock } from 'vitest';
import { useRunStore } from './runStore';
import type { BriefEvent } from '../lib/types';

// Mock the sse module before importing the store
vi.mock('../lib/sse', () => ({
  streamBrief: vi.fn(),
}));

// Import the mocked function after vi.mock
import { streamBrief } from '../lib/sse';

const mockStreamBrief = streamBrief as Mock<typeof streamBrief>;

describe('runStore.startRun', () => {
  beforeEach(() => {
    useRunStore.getState().reset();
    vi.clearAllMocks();
  });

  it('sets status to streaming immediately and reflects events from the stream', async () => {
    // Arrange: mock streamBrief to emit two events then resolve
    const events: BriefEvent[] = [
      {
        event: 'run_started',
        data: {
          run_id: 'test-run-1',
          ticker: 'MSFT',
          name: 'Microsoft Corporation',
          period: '3mo',
          model: 'test-model',
        },
      },
      {
        event: 'tool_call',
        data: { seq: 1, name: 'market_data', input: { ticker: 'MSFT' } },
      },
    ];

    mockStreamBrief.mockImplementation(
      async (
        _req,
        onEvent: (ev: BriefEvent) => void
      ): Promise<void> => {
        for (const ev of events) {
          onEvent(ev);
        }
      }
    );

    // Act
    useRunStore.getState().startRun('MSFT', '3mo');

    // Status is streaming immediately (set synchronously before the async call)
    expect(useRunStore.getState().status).toBe('streaming');
    expect(useRunStore.getState().ticker).toBe('MSFT');
    expect(useRunStore.getState().period).toBe('3mo');

    // Wait for the promise microtasks to flush
    await vi.waitFor(() => {
      const state = useRunStore.getState();
      // run_started overwrites name; tool_call adds to log
      expect(state.name).toBe('Microsoft Corporation');
      expect(state.log.length).toBe(1);
      expect(state.log[0].type).toBe('tool_call');
    });
  });

  it('sets status to error with message when the stream rejects', async () => {
    // Arrange: mock streamBrief to reject
    mockStreamBrief.mockRejectedValue(new Error('HTTP 503'));

    // Act
    useRunStore.getState().startRun('AAPL', '1mo');

    // Wait for the rejection to be handled
    await vi.waitFor(() => {
      const state = useRunStore.getState();
      expect(state.status).toBe('error');
      expect(state.error).toBe('HTTP 503');
    });
  });

  it('does not set error when the abort is triggered via stopRun', async () => {
    // Arrange: mock streamBrief to wait and then check if aborted
    let capturedSignal: AbortSignal | undefined;
    mockStreamBrief.mockImplementation(
      async (
        _req,
        _onEvent: (ev: BriefEvent) => void,
        signal?: AbortSignal
      ): Promise<void> => {
        capturedSignal = signal;
        // Simulate a slow stream that never finishes — resolves after being aborted
        await new Promise<void>((_resolve, reject) => {
          if (signal) {
            signal.addEventListener('abort', () => {
              reject(new DOMException('AbortError', 'AbortError'));
            });
          }
        });
      }
    );

    useRunStore.getState().startRun('TSLA', '6mo');
    expect(useRunStore.getState().status).toBe('streaming');

    // Stop the run — should abort the controller
    useRunStore.getState().stopRun();
    expect(useRunStore.getState().status).toBe('stopped');
    expect(capturedSignal?.aborted).toBe(true);

    // Give microtasks a chance to settle — error should NOT be set
    await new Promise((r) => setTimeout(r, 0));
    expect(useRunStore.getState().status).toBe('stopped');
    expect(useRunStore.getState().error).toBeNull();
  });
});
