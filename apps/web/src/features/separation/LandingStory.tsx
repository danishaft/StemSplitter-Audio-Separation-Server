import { Icon } from "./Icon";

const sessionLanes = [
  {
    label: "Original",
    path: "M0 24 C10 4 18 45 30 22 S48 5 60 25 76 42 88 19 100 24",
    state: "Reference",
  },
  {
    label: "Vocals",
    path: "M0 25 C12 25 16 7 26 20 S42 42 50 22 66 8 76 25 90 39 100 23",
    state: "Published",
  },
  {
    label: "Drums",
    path: "M0 25 L8 25 10 5 13 43 17 25 34 25 36 10 39 39 43 25 64 25 67 6 70 42 74 25 100 25",
    state: "Published",
  },
  {
    label: "Guitar",
    path: "M0 27 C9 15 18 15 27 27 S45 39 54 26 72 14 81 25 92 34 100 28",
    state: "Candidate",
  },
] as const;

export function LandingStory() {
  return (
    <>
      <section className="editorial-stage" id="standards" aria-labelledby="standards-title">
        <div className="editorial-stage__lead">
          <p className="eyebrow eyebrow--ink">The work after separation</p>
          <h2 id="standards-title">Hear relationships, not isolated downloads.</h2>
          <p>
            StemSplitter keeps the source, every released stem, and every
            quality decision inside one listening context.
          </p>
        </div>
        <div
          aria-label="Session anatomy showing an original recording and synchronized stem lanes with visible release states"
          className="editorial-stage__session"
          role="img"
        >
          <div className="session-anatomy__header">
            <div>
              <span>Session anatomy</span>
              <strong>One timeline. Every decision.</strong>
            </div>
            <span>Source / stems / release</span>
          </div>
          <div className="session-anatomy__ruler">
            <span>00:00</span>
            <span>01:12</span>
            <span>02:24</span>
            <span>03:36</span>
          </div>
          <div className="session-anatomy__lanes">
            <span className="session-anatomy__playhead" />
            {sessionLanes.map((lane) => (
              <div className="session-anatomy__lane" key={lane.label}>
                <strong>{lane.label}</strong>
                <svg aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 100 50">
                  <path d={lane.path} />
                </svg>
                <span data-state={lane.state.toLowerCase()}>{lane.state}</span>
              </div>
            ))}
          </div>
          <div className="session-anatomy__footer">
            <span>Release ledger</span>
            <p>Published audio exports. Candidate audio stays visible without entering the final bundle.</p>
          </div>
        </div>
        <div className="editorial-stage__details">
          <article>
            <h3>Everything stays together.</h3>
            <p>One transport owns playback, seeking, mute, solo, and level across every published stem.</p>
          </article>
          <article>
            <h3>Uncertainty stays visible.</h3>
            <p>Candidate, rejected, and missing audio never masquerades as a finished result.</p>
          </article>
          <article>
            <h3>The session leaves cleanly.</h3>
            <p>Export individual WAVs or complete bundles without breaking the listening flow.</p>
          </article>
        </div>
      </section>

      <section className="closing-media" aria-labelledby="closing-title">
        <div className="closing-media__veil" />
        <div className="closing-media__content">
          <p className="eyebrow">Ready when the record is</p>
          <h2 id="closing-title">Bring the next mix into focus.</h2>
          <a className="primary-action" href="#studio">
            Choose a track <Icon name="arrow" size={19} />
          </a>
        </div>
      </section>
    </>
  );
}
