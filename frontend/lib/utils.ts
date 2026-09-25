import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * tailwind-merge, taught our theme.
 *
 * Out of the box it only knows Tailwind's stock scales. Faced with
 * `text-h1 text-espresso` it cannot tell that the first is a font size and
 * the second a colour, so it assumes both are colours, calls them a conflict
 * and drops the size — which is how every Stat on the page once quietly
 * rendered at body size.
 *
 * Anything added to @theme in globals.css belongs in the matching list below.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ['eyebrow', 'small', 'body', 'lead', 'h3', 'h2', 'h1', 'hero'],
      color: [
        'cream', 'cream-2', 'ivory', 'sand', 'sand-2', 'taupe', 'taupe-2',
        'espresso', 'espresso-2', 'espresso-3', 'charcoal', 'ink-on-dark',
        'line', 'line-soft',
        'ai', 'ai-2', 'ai-soft', 'ai-line',
        'rule', 'rule-2', 'rule-soft', 'rule-line',
        'verified', 'verified-dim', 'warning', 'warning-dim', 'warning-glow',
        'critical', 'critical-dim', 'alert', 'info', 'info-dim',
      ],
      font: ['display', 'sans', 'mono'],
      radius: ['sm', 'md', 'lg', 'xl'],
      shadow: ['card', 'float', 'glass', 'ai', 'rule'],
      animate: ['pulse-ring', 'shimmer', 'marquee', 'float-slow', 'rise'],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
