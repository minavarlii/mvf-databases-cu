import type { Chunk } from '../api'

export type Tone = 'lav' | 'sky' | 'peach' | 'mint' | 'butter'

const TONES: Tone[] = ['lav', 'sky', 'peach', 'mint', 'butter']

export function articleTones(chunks: Chunk[]): Map<number, Tone> {
  const tones = new Map<number, Tone>()
  for (const c of chunks) {
    if (!tones.has(c.article_id)) tones.set(c.article_id, TONES[tones.size % TONES.length])
  }
  return tones
}

export const paletteTone = (i: number): Tone => TONES[i % TONES.length]
