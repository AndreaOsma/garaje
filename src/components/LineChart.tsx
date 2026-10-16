import { useEffect, useRef, useState } from "react";
import { num } from "../format";

type Props = {
  points: [number, number][];
  unit: string;
  label: string;
  height?: number;
};

const PAD = { top: 10, right: 8, bottom: 20, left: 40 };

/** Línea de una sola serie (sin leyenda: el título la nombra) con crosshair + tooltip. */
export function LineChart({ points, unit, label, height = 140 }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (points.length < 2) return <p className="muted">Pocos datos para dibujar una gráfica.</p>;

  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  if (y0 === y1) [y0, y1] = [y0 - 1, y1 + 1];
  const innerW = width - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const sx = (x: number) => PAD.left + ((x - x0) / (x1 - x0 || 1)) * innerW;
  const sy = (y: number) => PAD.top + (1 - (y - y0) / (y1 - y0)) * innerH;
  const path = points.map(([x, y], i) => `${i ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join("");
  const time = (ms: number) => new Date(ms).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = x0 + ((e.clientX - rect.left) / rect.width) * (x1 - x0);
    let best = 0;
    for (let i = 1; i < points.length; i++) if (Math.abs(points[i][0] - x) < Math.abs(points[best][0] - x)) best = i;
    setHover(best);
  }

  const hp = hover != null ? points[hover] : null;

  return (
    <div className="line-chart" ref={wrapRef}>
      <svg width={width} height={height} role="img" aria-label={`${label}: de ${num(y0)} a ${num(y1)} ${unit}`}>
        {[y0, (y0 + y1) / 2, y1].map((v) => (
          <g key={v}>
            <line className="line-chart__grid" x1={PAD.left} x2={width - PAD.right} y1={sy(v)} y2={sy(v)} />
            <text className="line-chart__axis" x={PAD.left - 6} y={sy(v) + 4} textAnchor="end">
              {num(v)}
            </text>
          </g>
        ))}
        <text className="line-chart__axis" x={PAD.left} y={height - 4}>
          {time(x0)}
        </text>
        <text className="line-chart__axis" x={width - PAD.right} y={height - 4} textAnchor="end">
          {time(x1)}
        </text>
        <path className="line-chart__line" d={path} />
        {hp && (
          <>
            <line className="line-chart__crosshair" x1={sx(hp[0])} x2={sx(hp[0])} y1={PAD.top} y2={PAD.top + innerH} />
            <circle className="line-chart__dot" cx={sx(hp[0])} cy={sy(hp[1])} r={4} />
          </>
        )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerW}
          height={innerH}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hp && (
        <div
          className="line-chart__tooltip"
          style={{ left: Math.min(sx(hp[0]) + 8, width - 120), top: Math.max(sy(hp[1]) - 34, 0) }}
          aria-hidden
        >
          <strong>
            {num(hp[1], 2)} {unit}
          </strong>
          <span>{time(hp[0])}</span>
        </div>
      )}
    </div>
  );
}
