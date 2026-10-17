import { useLayoutEffect, useRef, useState } from 'react'

// Real pixel width rather than a scaled viewBox, so chart text is the same size on every screen.
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(Math.floor(el.getBoundingClientRect().width))
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

function niceStep(raw: number): number {
  const power = 10 ** Math.floor(Math.log10(raw))
  const f = raw / power
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * power
}

export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1]
  const step = niceStep(max / count)
  const ticks: number[] = []
  for (let t = 0; t < max + step * 0.999; t += step) ticks.push(Number(t.toPrecision(12)))
  return ticks
}

export function barUp(x: number, y: number, w: number, baseline: number): string {
  const r = Math.min(4, w / 2, baseline - y)
  return `M${x},${baseline}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${baseline}Z`
}

export function barRight(baseline: number, y: number, len: number, h: number): string {
  const r = Math.min(4, h / 2, len)
  const x = baseline + len
  return `M${baseline},${y}H${x - r}Q${x},${y} ${x},${y + r}V${y + h - r}Q${x},${y + h} ${x - r},${y + h}H${baseline}Z`
}

export const formatMs = (v: number) => (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2))
