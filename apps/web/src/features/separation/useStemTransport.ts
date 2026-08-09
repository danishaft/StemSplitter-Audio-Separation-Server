import { useEffect, useEffectEvent, useRef, useState } from "react";

export interface StemTrack {
  id: string;
  src: string;
}

interface StemTransportOptions {
  duration: number;
  muted: Set<string>;
  soloed: Set<string>;
  tracks: StemTrack[];
  volumes: Record<string, number>;
}

export function useStemTransport({
  duration: analysisDuration,
  muted,
  soloed,
  tracks,
  volumes
}: StemTransportOptions) {
  const media = useRef(new Map<string, HTMLAudioElement>());
  const frame = useRef<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(analysisDuration);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const trackSignature = tracks.map((track) => `${track.id}:${track.src}`).join("|");

  const syncMixerState = useEffectEvent(() => {
    const hasSolo = soloed.size > 0;
    for (const [id, audio] of media.current) {
      audio.muted = muted.has(id) || (hasSolo && !soloed.has(id));
      audio.volume = Math.min(1, Math.max(0, volumes[id] ?? 1));
    }
  });

  useEffect(() => {
    for (const audio of media.current.values()) audio.pause();
    media.current.clear();
    setPlaying(false);
    setCurrentTime(0);
    setDuration(analysisDuration);

    for (const track of tracks) {
      const audio = new Audio(track.src);
      audio.preload = "metadata";
      audio.addEventListener("loadedmetadata", () => {
        if (Number.isFinite(audio.duration)) {
          setDuration((value) => Math.max(value, audio.duration));
        }
      });
      media.current.set(track.id, audio);
    }
    syncMixerState();

    return () => {
      if (frame.current != null) cancelAnimationFrame(frame.current);
      for (const audio of media.current.values()) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      media.current.clear();
    };
  }, [analysisDuration, trackSignature]);

  useEffect(() => {
    syncMixerState();
  }, [muted, soloed, volumes]);

  useEffect(() => {
    if (!playing) return undefined;
    function update(): void {
      const primary = media.current.values().next().value as HTMLAudioElement | undefined;
      if (!primary || primary.ended) {
        setPlaying(false);
        return;
      }
      const time = primary.currentTime || 0;
      setCurrentTime(time);
      for (const audio of media.current.values()) {
        if (audio === primary || audio.paused || Math.abs(audio.currentTime - time) < 0.12) continue;
        audio.currentTime = time;
      }
      frame.current = requestAnimationFrame(update);
    }
    frame.current = requestAnimationFrame(update);
    return () => {
      if (frame.current != null) cancelAnimationFrame(frame.current);
    };
  }, [playing]);

  function seek(seconds: number): void {
    const next = Math.min(duration || 0, Math.max(0, seconds));
    for (const audio of media.current.values()) {
      if (audio.readyState > 0) audio.currentTime = next;
    }
    setCurrentTime(next);
  }

  async function toggle(): Promise<void> {
    setError("");
    if (playing) {
      for (const audio of media.current.values()) audio.pause();
      setPlaying(false);
      return;
    }
    const elements = [...media.current.values()];
    if (!elements.length) return;
    for (const audio of elements) {
      if (audio.readyState > 0) audio.currentTime = currentTime;
    }
    const results = await Promise.allSettled(elements.map((audio) => audio.play()));
    if (results.every((result) => result.status === "rejected")) {
      setError("Playback could not start. The stem downloads are still available.");
      return;
    }
    setPlaying(true);
  }

  return { currentTime, duration, error, playing, seek, toggle };
}
