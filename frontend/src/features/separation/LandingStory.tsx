import { Icon } from "./Icon";

interface ProductProofProps {
  supportedCount: number;
}

export function ProductProof({ supportedCount }: ProductProofProps) {
  return (
    <section className="proof-band" id="product-proof" aria-labelledby="proof-title">
      <div className="proof-band__heading">
        <p className="eyebrow eyebrow--ink">Built around the music</p>
        <h2 id="proof-title">One song in. A real session out.</h2>
      </div>
      <div className="proof-band__grid">
        <article>
          <span>01</span>
          <h3>One shared clock</h3>
          <p>Every published stem stays aligned on the same timeline and playhead.</p>
        </article>
        <article>
          <span>02</span>
          <h3>{supportedCount || "Multiple"} target stems</h3>
          <p>Hear the supported families without turning candidate audio into a false promise.</p>
        </article>
        <article>
          <span>03</span>
          <h3>Professional handoff</h3>
          <p>Audition individual parts, inspect quality, then export stems or the complete bundle.</p>
        </article>
      </div>
    </section>
  );
}

export function LandingStory() {
  return (
    <>
      <section className="workflow" aria-labelledby="workflow-title">
        <div className="workflow__copy">
          <p className="eyebrow eyebrow--ink">A clear signal path</p>
          <h2 id="workflow-title">From finished mix to working session.</h2>
          <p>
            No maze of tools. Bring in the track, choose the separation depth,
            and move directly into synchronized critical listening.
          </p>
        </div>
        <ol className="workflow__steps">
          <li><span>01</span><div><b>Bring the record</b><p>Upload studio audio or import an eligible Audius release.</p></div></li>
          <li><span>02</span><div><b>Separate with context</b><p>Keep source identity visible through queueing, inference, and recovery.</p></div></li>
          <li><span>03</span><div><b>Listen before export</b><p>Solo, mute, balance, compare, and download only the outputs you trust.</p></div></li>
        </ol>
      </section>

      <section className="standards" id="standards" aria-labelledby="standards-title">
        <div className="standards__signal" aria-hidden="true">
          <span /><span /><span /><span /><span /><span /><span /><span /><span /><span />
          <span /><span /><span /><span /><span /><span /><span /><span /><span /><span />
          <span /><span /><span /><span /><span /><span /><span /><span /><span /><span />
        </div>
        <div className="standards__copy">
          <p className="eyebrow">Quality without the theatre</p>
          <h2 id="standards-title">If a stem is uncertain, the interface says so.</h2>
          <p>
            Published, candidate, rejected, and missing outputs stay distinct.
            Completed work remains usable even when an optional specialist does not pass.
          </p>
          <a className="standards__link" href="#studio">
            Open the studio <Icon name="arrow" size={18} />
          </a>
        </div>
      </section>

      <section className="closing-cta" aria-labelledby="closing-title">
        <p className="eyebrow eyebrow--ink">Your next session starts here</p>
        <h2 id="closing-title">Hear what the mix has been hiding.</h2>
        <a className="closing-cta__action" href="#studio">
          Choose a track <Icon name="arrow" size={20} />
        </a>
      </section>
    </>
  );
}
