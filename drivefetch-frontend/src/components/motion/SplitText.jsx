import { Fragment } from 'react';

/**
 * Splits text into words that each rise out of their own mask (see .df-split in
 * index.css). `start` offsets the word index so several lines can share one
 * running stagger. The words stay real text (separated by spaces), so screen
 * readers and search engines read the sentence normally.
 */
export default function SplitText({ text, as: Tag = 'span', className = '', start = 0, delay = 0, reveal = true, ...rest }) {
  const words = String(text).split(/\s+/).filter(Boolean);
  return (
    <Tag
      className={`df-split ${className}`}
      {...(reveal ? { 'data-reveal': 'split' } : {})}
      style={delay ? { '--rd': `${delay}ms` } : undefined}
      {...rest}
    >
      {words.map((w, i) => (
        <Fragment key={`${w}-${i}`}>
          <span className="df-w">
            <span className="df-wi" style={{ '--i': start + i }}>{w}</span>
          </span>
          {i < words.length - 1 ? ' ' : null}
        </Fragment>
      ))}
    </Tag>
  );
}
