/**
 * Minimal markdown renderer for AI answers and notes.
 *
 * Deliberately not a full markdown library: the model emits bold, bullets and
 * numbered lists, and pulling in a parser plus sanitizer for that would be a
 * lot of bytes. Only inline `**bold**` and `` `code` `` are interpreted, and
 * everything is rendered as text nodes, so nothing here can inject HTML.
 */

import type { ReactNode } from 'react';

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`)/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={key} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={key} className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={key}>{part}</span>;
  });
}

export function Markdown({ content }: { content: string }) {
  const lines = content.split('\n');
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? 'ol' : 'ul';
    blocks.push(
      <Tag
        key={`list-${blocks.length}`}
        className={`my-1 space-y-0.5 pl-4 ${list.ordered ? 'list-decimal' : 'list-disc'}`}
      >
        {list.items.map((item, i) => (
          <li key={i}>{renderInline(item, `li-${blocks.length}-${i}`)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };

  lines.forEach((raw, index) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);

    if (bullet) {
      if (!list || list.ordered) {
        flush();
        list = { ordered: false, items: [] };
      }
      list.items.push(bullet[1]);
      return;
    }
    if (numbered) {
      if (!list || !list.ordered) {
        flush();
        list = { ordered: true, items: [] };
      }
      list.items.push(numbered[1]);
      return;
    }

    flush();
    if (!line.trim()) return;

    const heading = line.match(/^#{1,6}\s+(.*)$/);
    if (heading) {
      blocks.push(
        <p key={index} className="mt-2 font-semibold text-ink">
          {renderInline(heading[1], `h-${index}`)}
        </p>,
      );
      return;
    }

    blocks.push(
      <p key={index} className="my-1">
        {renderInline(line, `p-${index}`)}
      </p>,
    );
  });

  flush();
  return <div className="[&>*:first-child]:mt-0">{blocks}</div>;
}
