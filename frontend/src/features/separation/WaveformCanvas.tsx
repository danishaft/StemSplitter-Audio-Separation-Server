import { useEffect, useRef } from "react";

interface WaveformCanvasProps {
  color: string;
  currentTime: number;
  duration: number;
  label: string;
  onSeek: (seconds: number) => void;
  peaks?: number[];
}

export function WaveformCanvas({
  color,
  currentTime,
  duration,
  label,
  onSeek,
  peaks
}: WaveformCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !peaks?.length) return undefined;
    const context = canvas.getContext("2d");
    if (!context) return undefined;
    const target = canvas;
    const drawContext = context;
    const drawPeaks = peaks;

    function draw(): void {
      const bounds = target.getBoundingClientRect();
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      target.width = Math.max(1, Math.round(bounds.width * scale));
      target.height = Math.max(1, Math.round(bounds.height * scale));
      drawContext.setTransform(scale, 0, 0, scale, 0, 0);
      drawContext.clearRect(0, 0, bounds.width, bounds.height);

      const gap = bounds.width < 520 ? 3 : 4;
      const barWidth = Math.max(1, gap * 0.48);
      const visibleBars = Math.max(1, Math.floor(bounds.width / gap));
      const step = drawPeaks.length / visibleBars;
      const center = bounds.height / 2;
      const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0;

      for (let index = 0; index < visibleBars; index += 1) {
        const peak = drawPeaks[Math.min(drawPeaks.length - 1, Math.floor(index * step))] || 0;
        const height = Math.max(2, peak * (bounds.height - 10));
        drawContext.globalAlpha = index / visibleBars <= progress ? 1 : 0.62;
        drawContext.fillStyle = color;
        drawContext.beginPath();
        drawContext.roundRect(index * gap, center - height / 2, barWidth, height, barWidth / 2);
        drawContext.fill();
      }

      drawContext.globalAlpha = 0.86;
      drawContext.fillStyle = "#f4f8ff";
      drawContext.fillRect(progress * bounds.width, 0, 1.5, bounds.height);
      drawContext.globalAlpha = 1;
    }

    const observer = new ResizeObserver(draw);
    observer.observe(target);
    draw();
    return () => observer.disconnect();
  }, [color, currentTime, duration, peaks]);

  function seek(clientX: number): void {
    const bounds = canvasRef.current?.getBoundingClientRect();
    if (!bounds || duration <= 0) return;
    const ratio = Math.min(1, Math.max(0, (clientX - bounds.left) / bounds.width));
    onSeek(ratio * duration);
  }

  if (!peaks?.length) {
    return <div className="waveform waveform--unavailable">Waveform analysis unavailable</div>;
  }

  return (
    <canvas
      aria-label={`Seek ${label}`}
      aria-valuemax={Math.round(duration)}
      aria-valuemin={0}
      aria-valuenow={Math.round(currentTime)}
      className="waveform"
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault();
          onSeek(currentTime + (event.key === "ArrowRight" ? 5 : -5));
        }
      }}
      onPointerDown={(event) => seek(event.clientX)}
      ref={canvasRef}
      role="slider"
      tabIndex={0}
    />
  );
}
