import React, { useMemo } from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { theme } from '../theme';

type Word = { word: string; start: number; end: number };
type Sentence = { words: Word[]; start: number; end: number };

const SENTENCE_MAX_WORDS = 9;
const SENTENCE_END = /[.?!]$/;

const wordsToSentences = (words: Word[]): Sentence[] => {
  const out: Sentence[] = [];
  let buf: Word[] = [];

  const flush = () => {
    if (!buf.length) return;
    out.push({
      words: [...buf],
      start: buf[0].start,
      end: buf[buf.length - 1].end,
    });
    buf = [];
  };

  for (const w of words) {
    buf.push(w);
    if (SENTENCE_END.test(w.word) || buf.length >= SENTENCE_MAX_WORDS) flush();
  }
  flush();
  return out;
};

export const LiveCaption: React.FC<{
  words: Word[];
  voiceStartSec: number;
}> = ({ words, voiceStartSec }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sentences = useMemo(() => wordsToSentences(words || []), [words]);
  if (!sentences.length) return null;

  const t = frame / fps - voiceStartSec;
  const current = sentences.find((s) => t >= s.start && t < s.end);
  if (!current) return null;

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        padding: '0 80px 70px',
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          fontFamily: theme.inter,
          fontSize: 26,
          fontWeight: 500,
          lineHeight: 1.55,
          letterSpacing: '-0.005em',
          color: 'rgba(255,255,255,0.96)',
          textAlign: 'center',
          textShadow: '0 1px 3px rgba(0,0,0,0.6), 0 4px 16px rgba(0,0,0,0.4)',
          padding: '10px 18px',
          borderRadius: 10,
          background: 'rgba(0,0,0,0.32)',
          backdropFilter: 'blur(14px) saturate(1.2)',
          WebkitBackdropFilter: 'blur(14px) saturate(1.2)',
          border: '1px solid rgba(255,255,255,0.06)',
          maxWidth: '72%',
        }}
      >
        {current.words.map((w, i) => {
          const isActive = t >= w.start && t < w.end;
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                margin: '0 2px',
                borderRadius: 6,
                background: isActive ? theme.gold : 'transparent',
                color: isActive ? '#1a1a1a' : 'rgba(255,255,255,0.96)',
                fontWeight: isActive ? 700 : 500,
                transform: isActive ? 'translateY(-1px) scale(1.04)' : 'none',
                transformOrigin: 'center bottom',
                textShadow: isActive ? 'none' : '0 1px 3px rgba(0,0,0,0.6)',
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
