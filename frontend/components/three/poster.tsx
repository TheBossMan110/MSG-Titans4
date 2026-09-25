/**
 * The static stand-in for the 3D engine: six slabs, drawn once, no runtime.
 *
 * Shown under 1024px, when motion is reduced, and for the instant before the
 * WebGL scene mounts so the hero never has a hole in it.
 */
export function EnginePoster({ className }: { className?: string }) {
  const slabs = [
    { fill: '#FBF8F2', stroke: '#D8CCB9', dash: false },
    { fill: '#E7DCCB', stroke: '#A08B75', dash: true },
    { fill: '#D9CBB5', stroke: '#C4B29A', dash: false },
    { fill: '#A08B75', stroke: '#7D6A57', dash: false },
    { fill: '#2A1F17', stroke: '#2A1F17', dash: false },
    { fill: '#F1EBE1', stroke: '#D8CCB9', dash: false },
  ]
  return (
    <svg viewBox="0 0 520 420" className={className} role="img" aria-label="Six stacked slabs: complaint, AI, knowledge, rules, validation, resolution">
      <defs>
        <radialGradient id="shadow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#2A1F17" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#2A1F17" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx="262" cy="372" rx="190" ry="34" fill="url(#shadow)" />
      {slabs.map((s, i) => {
        const y = 300 - i * 44
        return (
          <g key={i} transform={`translate(0 ${y})`}>
            <path
              d="M120 40 L300 -10 L420 40 L240 90 Z"
              fill={s.fill}
              stroke={s.stroke}
              strokeWidth={1.5}
              strokeDasharray={s.dash ? '6 5' : undefined}
              strokeLinejoin="round"
            />
            <path d="M120 40 L240 90 L240 104 L120 54 Z" fill={s.fill} opacity={0.82} stroke={s.stroke} strokeWidth={1} />
            <path d="M240 90 L420 40 L420 54 L240 104 Z" fill={s.fill} opacity={0.65} stroke={s.stroke} strokeWidth={1} />
          </g>
        )
      })}
    </svg>
  )
}
