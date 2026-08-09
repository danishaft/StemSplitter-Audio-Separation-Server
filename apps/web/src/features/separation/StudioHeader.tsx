import {
  SignInButton,
  SignUpButton,
  Show,
  UserButton
} from "@clerk/nextjs";

import { Icon } from "./Icon";

interface StudioHeaderProps {
  hasSession: boolean;
}

export function StudioHeader({
  hasSession
}: StudioHeaderProps) {
  return (
    <>
      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="StemSplitter home">
          <span className="wordmark__mark"><Icon name="wave" size={20} /></span>
          <span>STEM<span className="wordmark__slash">/</span>SPLITTER</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#studio">Studio</a>
          <a href="#standards">Output standards</a>
        </nav>
        <div className="header-actions">
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button className="header-sign-in" type="button">Sign in</button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="header-cta" type="button">Create account</button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <a className="header-cta" href={hasSession ? "#results" : "#studio"}>
              {hasSession ? "Open session" : "Split a track"}
            </a>
            <UserButton />
          </Show>
        </div>
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
            <p className="hero__product">StemSplitter <span>Studio</span></p>
            <h1 id="hero-title">Turn one song into a working session.</h1>
            <p className="hero__lede">
              Separate, audition, and export synchronized stems without losing
              sight of the record they came from.
            </p>
            <div className="hero__actions">
              <a className="primary-action" href="#studio">
                Open the studio <Icon name="arrow" size={19} />
              </a>
            </div>
            <p className="hero__assurance">Local upload or Audius import · synchronized playback · quality-gated export</p>
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
