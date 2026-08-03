const AUDIO_EXTENSIONS = /\.(flac|m4a|mp3|ogg|wav)(\?.*)?$/i;

interface ArtifactCardProps {
  name: string;
  href: string;
  parent?: boolean;
}

export function ArtifactCard({ name, href, parent = false }: ArtifactCardProps) {
  return (
    <article className={`stem-card ${parent ? "stem-card--parent" : ""}`}>
      <strong>{name.replaceAll("_", " ")}</strong>
      <small>{parent ? "parent stem" : "child stem"}</small>
      {AUDIO_EXTENSIONS.test(href) ? <audio controls preload="none" src={href} /> : null}
      <a href={href} download target="_blank" rel="noreferrer">
        Download
      </a>
    </article>
  );
}
