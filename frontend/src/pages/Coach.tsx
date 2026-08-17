/**
 * AI Coach.
 *
 * All inference goes through FastAPI — the browser never sees a Groq key.
 * When AI is unavailable the deterministic fallback renders in its place, so
 * this page is never empty.
 */

import { useEffect, useRef, useState } from 'react';
import { RotateCcw, Send, Sparkles, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { api, type Insight } from '../lib/api';
import { useApi } from '../hooks/useApi';
import { AICoachCard } from '../components/AICoachCard';
import { Card, Empty, Loading } from '../components/ui';
import { Markdown } from '../components/Markdown';

const TABS = [
  { id: 'daily', label: 'Daily insight' },
  { id: 'weekly', label: 'Weekly review' },
  { id: 'weaknesses', label: 'Weakness analysis' },
  { id: 'plan', label: 'Study plan' },
] as const;

type TabId = (typeof TABS)[number]['id'];

const SUGGESTIONS = [
  'Why am I weak at DP?',
  'What should I solve tonight?',
  'Am I actually improving?',
  'Why has my Codeforces rating stopped increasing?',
  'Which topics have I neglected?',
  'Show me my recurring mistakes.',
];

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
  failed?: boolean;
}

export function Coach() {
  const [tab, setTab] = useState<TabId>('daily');
  const status = useApi(() => api.aiStatus(), []);

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-accent" />
          <h1 className="text-lg font-semibold">AI Coach</h1>
        </div>
        {status.data && (
          <div className="flex items-center gap-3 text-xs text-ink-dim">
            {status.data.available ? (
              <>
                <span className="font-mono">{status.data.model}</span>
                <span>
                  {status.data.requests_today}/{status.data.daily_budget} requests today
                </span>
              </>
            ) : (
              <span className="text-accent">{status.data.reason}</span>
            )}
          </div>
        )}
      </div>

      {status.data && !status.data.available && (
        <div className="card px-4 py-3 text-sm text-ink-muted">
          AI Coach is unavailable — {status.data.reason} Your deterministic analytics,
          recommendations and review queue all still work, and the panels below fall back to them.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <div className="flex flex-wrap gap-1.5">
            {TABS.map((item) => (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                className={clsx('btn', tab === item.id ? 'btn-primary' : 'btn-ghost')}
              >
                {item.label}
              </button>
            ))}
          </div>
          <InsightPanel tab={tab} />
        </div>

        <div className="lg:col-span-2">
          <ChatPanel available={status.data?.available ?? false} />
        </div>
      </div>
    </div>
  );
}

function InsightPanel({ tab }: { tab: TabId }) {
  const [refreshing, setRefreshing] = useState(false);

  const fetcher = () => {
    switch (tab) {
      case 'weekly':
        return api.aiWeekly();
      case 'weaknesses':
        return api.aiWeaknesses();
      case 'plan':
        return api.aiStudyPlan();
      default:
        return api.aiDaily();
    }
  };

  const { data, loading, reload } = useApi<Insight>(fetcher, [tab]);

  async function refresh() {
    setRefreshing(true);
    try {
      if (tab === 'weekly') await api.aiWeekly(true);
      else if (tab === 'weaknesses') await api.aiWeaknesses(true);
      else if (tab === 'plan') await api.aiStudyPlan(true);
      else await api.aiDaily(true);
      reload();
    } finally {
      setRefreshing(false);
    }
  }

  const structured = data?.structured_output ?? null;

  return (
    <div className="space-y-4">
      <AICoachCard insight={data} loading={loading} onRefresh={refresh} refreshing={refreshing} />

      {structured?.weaknesses && structured.weaknesses.length > 0 && (
        <Card title="Diagnosed weaknesses">
          <ul className="divide-y divide-line">
            {structured.weaknesses.map((item, i) => (
              <li key={i} className="px-4 py-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{item.topic}</span>
                  <span
                    className={clsx(
                      'text-[11px] uppercase',
                      item.severity === 'high'
                        ? 'text-danger'
                        : item.severity === 'medium'
                          ? 'text-accent'
                          : 'text-ink-dim',
                    )}
                  >
                    {item.severity}
                  </span>
                </div>
                <p className="mt-1 text-xs text-ink-dim">{item.root_cause}</p>
                <ul className="mt-1.5 space-y-0.5">
                  {item.evidence.map((line, j) => (
                    <li key={j} className="text-xs text-ink-dim">
                      · {line}
                    </li>
                  ))}
                </ul>
                <p className="mt-1.5 text-sm text-ink-muted">{item.recommended_action}</p>
                {item.recommended_difficulty && (
                  <span className="chip mt-1.5">{item.recommended_difficulty}</span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {structured?.days && structured.days.length > 0 && (
        <Card title="This week's plan">
          <ul className="divide-y divide-line">
            {structured.days.map((day, i) => (
              <li key={i} className="px-4 py-3">
                <div className="flex items-baseline gap-2">
                  <span className="w-24 shrink-0 text-sm font-medium text-ink">{day.day}</span>
                  <span className="text-sm text-accent">{day.focus}</span>
                </div>
                <ul className="mt-1 space-y-0.5 pl-24">
                  {day.tasks.map((task, j) => (
                    <li key={j} className="text-xs text-ink-muted">
                      · {task}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          {structured.notes && structured.notes.length > 0 && (
            <div className="border-t border-line px-4 py-2.5">
              {structured.notes.map((note, i) => (
                <p key={i} className="text-xs text-ink-dim">
                  {note}
                </p>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function ChatPanel({ available }: { available: boolean }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pending]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;

    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setInput('');
    setPending(true);

    try {
      const response = await api.aiChat(question, conversationId);
      if (response.conversation_id) setConversationId(response.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          tools: response.tools_used,
          failed: !response.available,
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            error instanceof Error
              ? `Could not reach the coach: ${error.message}`
              : 'Something went wrong.',
          failed: true,
        },
      ]);
    } finally {
      setPending(false);
    }
  }

  const lastUser = [...messages].reverse().find((m) => m.role === 'user');

  return (
    <Card
      title="Ask the coach"
      subtitle="Answers are grounded in your recorded data"
      className="flex h-[70vh] flex-col lg:sticky lg:top-20"
      action={
        messages.length > 0 ? (
          <button
            onClick={() => {
              setMessages([]);
              setConversationId(undefined);
            }}
            className="text-ink-dim hover:text-ink"
            title="Clear conversation"
          >
            <Trash2 size={14} />
          </button>
        ) : undefined
      }
    >
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <div className="py-4">
            <Empty
              title="Ask about your own data"
              hint="The coach reads your real statistics before answering."
              icon={<Sparkles size={20} />}
            />
            <div className="mt-3 space-y-1.5">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => send(suggestion)}
                  disabled={!available}
                  className="w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-left text-xs text-ink-muted transition-colors hover:border-line-strong hover:text-ink disabled:opacity-40"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, i) => (
          <div
            key={i}
            className={clsx('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}
          >
            <div
              className={clsx(
                'max-w-[92%] rounded-xl px-3 py-2 text-sm leading-relaxed',
                message.role === 'user'
                  ? 'bg-accent text-surface-0'
                  : message.failed
                    ? 'bg-danger/10 text-danger'
                    : 'bg-surface-2 text-ink-muted',
              )}
            >
              {message.role === 'assistant' ? (
                <Markdown content={message.content} />
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}
              {message.tools && message.tools.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {message.tools.map((tool) => (
                    <span key={tool} className="chip font-mono text-[10px]">
                      {tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {pending && <Loading label="Reading your data" />}

        {!pending && messages.at(-1)?.failed && lastUser && (
          <button
            onClick={() => send(lastUser.content)}
            className="btn btn-ghost mx-auto"
          >
            <RotateCcw size={13} /> Retry
          </button>
        )}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
        className="flex items-center gap-2 border-t border-line px-3 py-2.5"
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={!available || pending}
          placeholder={available ? 'Ask about your progress…' : 'AI Coach unavailable'}
          className="w-full bg-transparent text-sm outline-none placeholder:text-ink-dim disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!available || pending || !input.trim()}
          className="btn btn-primary disabled:opacity-40"
        >
          <Send size={13} />
        </button>
      </form>
    </Card>
  );
}
