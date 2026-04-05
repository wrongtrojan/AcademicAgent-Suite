// components/MarkdownRenderer.tsx
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { memo } from 'react';

const MarkdownRenderer = memo(({ content }: { content: string }) => {
  return (
    // 使用 overflow-hidden 防止内部元素撑开瞬间溢出
    <div className="prose prose-invert max-w-none text-sm leading-relaxed overflow-hidden">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}, (prev, next) => prev.content === next.content);

export default MarkdownRenderer;