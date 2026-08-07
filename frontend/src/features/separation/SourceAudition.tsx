import { useEffect, useRef, useState } from "react";

import { Icon } from "./Icon";

interface SourceAuditionProps {
  file: File;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
}

export function SourceAudition({ file }: SourceAuditionProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playbackError, setPlaybackError] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);
    setSourceUrl(nextUrl);
    setCurrentTime(0);
    setDuration(0);
    setPlaying(false);
    setPlaybackError("");

    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio && sourceUrl) {
      audio.src = sourceUrl;
      audio.load();
    }

    return () => {
      if (animationRef.current != null) cancelAnimationFrame(animationRef.current);
      sourceRef.current?.disconnect();
      analyserRef.current?.disconnect();
      void audioContextRef.current?.close();
      sourceRef.current = null;
      analyserRef.current = null;
      audioContextRef.current = null;
    };
  }, [sourceUrl]);

  function stopSignal(): void {
    if (animationRef.current != null) cancelAnimationFrame(animationRef.current);
    animationRef.current = null;
  }

  function drawSignal(): void {
    const analyser = analyserRef.current;
    const canvas = canvasRef.current;
    if (!analyser || !canvas) return;

    const pixelRatio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(canvas.clientWidth * pixelRatio));
    const height = Math.max(1, Math.round(canvas.clientHeight * pixelRatio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    const context = canvas.getContext("2d");
    if (!context) return;
    const samples = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(samples);
    context.clearRect(0, 0, width, height);
    context.beginPath();
    samples.forEach((sample, index) => {
      const x = (index / (samples.length - 1)) * width;
      const y = (sample / 255) * height;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.lineWidth = 1.5 * pixelRatio;
    context.strokeStyle = getComputedStyle(canvas).color;
    context.stroke();
    animationRef.current = requestAnimationFrame(drawSignal);
  }

  async function togglePlayback(): Promise<void> {
    const audio = audioRef.current;
    if (!audio) return;

    try {
      if (!audioContextRef.current) {
        const audioContext = new AudioContext();
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = .72;
        const source = audioContext.createMediaElementSource(audio);
        source.connect(analyser);
        analyser.connect(audioContext.destination);
        audioContextRef.current = audioContext;
        analyserRef.current = analyser;
        sourceRef.current = source;
      }

      if (audio.paused) {
        setPlaybackError("");
        await audioContextRef.current.resume();
        await audio.play();
        setPlaying(true);
        drawSignal();
      } else {
        audio.pause();
        setPlaying(false);
        stopSignal();
      }
    } catch {
      setPlaying(false);
      stopSignal();
      setPlaybackError("This source cannot be played in your browser.");
    }
  }

  const progress = duration ? Math.min(100, (currentTime / duration) * 100) : 0;

  return (
    <section className="source-audition" aria-label="Selected source audition">
      <audio
        key={sourceUrl}
        onEnded={() => {
          setPlaying(false);
          stopSignal();
        }}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
        onError={() => setPlaybackError("This source cannot be played in your browser.")}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        ref={audioRef}
      />
      <button
        aria-label={playing ? "Pause source preview" : "Play source preview"}
        className="source-audition__play"
        onClick={() => void togglePlayback()}
        type="button"
      >
        <Icon name={playing ? "pause" : "play"} size={22} />
      </button>
      <div className="source-audition__signal">
        <div className="source-audition__meta">
          <span>Live source signal</span>
          <strong>{formatTime(currentTime)} / {formatTime(duration)}</strong>
        </div>
        <div className="source-audition__scope">
          <canvas aria-hidden="true" ref={canvasRef} />
          <span className="source-audition__playhead" style={{ left: `${progress}%` }} />
        </div>
        <input
          aria-label="Seek source preview"
          disabled={!duration}
          max={duration || 0}
          min="0"
          onChange={(event) => {
            const nextTime = Number(event.target.value);
            if (audioRef.current) audioRef.current.currentTime = nextTime;
            setCurrentTime(nextTime);
          }}
          step="0.01"
          type="range"
          value={currentTime}
        />
        {playbackError ? <p className="source-audition__error" role="status">{playbackError}</p> : null}
      </div>
    </section>
  );
}
