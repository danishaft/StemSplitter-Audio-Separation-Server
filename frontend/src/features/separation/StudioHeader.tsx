import { Icon } from "./Icon";

interface StudioHeaderProps {
  hasSession: boolean;
  supportedCount: number;
}

export function StudioHeader({
  hasSession,
  supportedCount
}: StudioHeaderProps) {
  return (
    <>
      <header className="site-header glass-panel">
        <a className="wordmark" href="#top" aria-label="StemSplitter home">
          <span className="wordmark__mark"><Icon name="wave" size={20} /></span>
          <span>STEM<span className="wordmark__slash">/</span>SPLITTER</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#product-proof">Product</a>
          <a href="#studio">Split a track</a>
          <a href="#standards">Standards</a>
        </nav>
        <a className="header-cta" href={hasSession ? "#results" : "#studio"}>
          {hasSession ? "Open session" : "Split a track"}
        </a>
      </header>

      {!hasSession ? (
        <section className="hero" aria-labelledby="hero-title">
          <video
            aria-hidden="true"
            autoPlay
            className="hero__video"
            loop
            muted
            playsInline
            poster="/media/studio-hero-poster.jpg"
          >
            <source src="/media/studio-hero.mp4" type="video/mp4" />
          </video>
          <div className="hero__veil" />
          <div className="hero__content">
            <p className="eyebrow">Separation for working musicians</p>
            <h1 id="hero-title">Find every part.<br />Keep what sounds right.</h1>
            <p className="hero__lede">
              Turn one finished mix into synchronized, quality-gated stems you
              can audition, compare, and take back into the studio.
            </p>
            <div className="hero__actions">
              <a className="primary-action" href="#studio">
                Split a track <Icon name="arrow" size={19} />
              </a>
              <a className="hero__secondary" href="#product-proof">See the workflow</a>
            </div>
            <div className="hero__facts" aria-label="Current release facts">
              <span><b>{supportedCount || "Multiple"}</b> target stems</span>
              <span><b>Upload + Audius</b> source paths</span>
              <span><b>Quality-gated</b> release</span>
            </div>
          </div>
          <a
            className="hero__credit"
            href="https://www.pexels.com/video/man-on-a-recording-studio-using-a-mixing-console-7586172/"
            rel="noreferrer"
            target="_blank"
          >
            Film: Los Muertos Crew / Pexels
          </a>
        </section>
      ) : null}
    </>
  );
}
