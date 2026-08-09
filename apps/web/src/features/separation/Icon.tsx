type IconName =
  | "arrow"
  | "check"
  | "download"
  | "file"
  | "pause"
  | "play"
  | "search"
  | "upload"
  | "wave";

interface IconProps {
  name: IconName;
  size?: number;
}

const paths: Record<IconName, React.ReactNode> = {
  arrow: <path d="m9 18 6-6-6-6M4 12h11" />,
  check: <path d="m5 12 4 4L19 6" />,
  download: <path d="M12 3v12m0 0 5-5m-5 5-5-5M5 21h14" />,
  file: <path d="M7 3h7l4 4v14H7V3Zm7 0v5h4" />,
  pause: <path d="M9 7v10m6-10v10" />,
  play: <path d="m9 6 9 6-9 6V6Z" />,
  search: <path d="m20 20-4.2-4.2M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z" />,
  upload: <path d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14" />,
  wave: <path d="M4 12h2l2-6 3 12 3-9 2 6 2-3h2" />
};

export function Icon({ name, size = 20 }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8">
        {paths[name]}
      </g>
    </svg>
  );
}
