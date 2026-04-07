import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import styles from './index.module.css';

const FEATURES = [
  {
    icon: '🔍',
    title: 'Evidence-First Architecture',
    description:
      'Every piece of text, shape, and image in your PPTX receives a stable, deterministic Evidence ID. No narration claim can exist without citing its source.',
  },
  {
    icon: '🛡️',
    title: 'Zero Hallucination Guarantee',
    description:
      'An iterative Verifier loop blocks any script segment that cannot be grounded in the evidence index. Image claims must cite image evidence — enforced automatically.',
  },
  {
    icon: '🎯',
    title: 'Visual Guidance Overlays',
    description:
      'HIGHLIGHT, TRACE, and ZOOM actions are generated from your diagram\'s actual graph structure, pinned to real shape coordinates — not guessed positions.',
  },
  {
    icon: '🕸️',
    title: 'Three-Layer Graph System',
    description:
      'A Native Graph (from PPT shapes), an optional Vision Graph (from OCR), and a Unified Graph with provenance tracking give the pipeline a structural model of every slide.',
  },
  {
    icon: '🌐',
    title: 'Multi-Language Output',
    description:
      'Generate narrated videos in multiple languages from a single pipeline run. Evidence and graphs are shared; only script, audio, and overlays are reproduced per language.',
  },
  {
    icon: '⚡',
    title: 'Quality Presets',
    description:
      'Switch between Draft (fast, no vision), Standard (subtitles + crossfade), and Pro (full vision, BGM ducking, loudness normalisation) with a single environment variable.',
  },
];

const PIPELINE_STAGES = [
  'Ingest PPTX',
  'Build Evidence Index',
  'Construct Graphs',
  'Render Slides',
  'Generate Script',
  'Verify & Rewrite',
  'Synthesise Audio',
  'Build Timeline',
  'Render Overlays',
  'Compose Video',
];

function Feature({ icon, title, description }) {
  return (
    <div className={clsx('col col--4')} style={{ marginBottom: '1.5rem' }}>
      <div className="feature-card">
        <span className="feature-card__icon">{icon}</span>
        <h3 className="feature-card__title">{title}</h3>
        <p style={{ color: 'var(--ifm-color-emphasis-700)', lineHeight: 1.65, margin: 0 }}>
          {description}
        </p>
      </div>
    </div>
  );
}

function HeroBanner() {
  const logoUrl = useBaseUrl('/img/logo.svg');
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <div style={{ marginBottom: '1.5rem' }}>
          <img src={logoUrl} alt="SlideSherlock" width={72} height={72} />
        </div>
        <h1 className="hero__title">SlideSherlock</h1>
        <p className="hero__subtitle">
          Turn any PowerPoint presentation into a professionally narrated explainer video — complete
          with visual guidance overlays and a hallucination-free narration pipeline backed by a
          cryptographic evidence index.
        </p>
        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link className="button button--primary button--lg" to="/docs/getting-started/quickstart">
            Get Started →
          </Link>
          <Link className="button button--outline button--lg" to="/docs/intro">
            How It Works
          </Link>
          <Link
            className="button button--outline button--lg"
            href="https://github.com/sachinkg12/SlideSherlock"
          >
            GitHub
          </Link>
        </div>

        {/* Pipeline strip */}
        <div style={{ marginTop: '3rem' }}>
          <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.78rem', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '0.75rem' }}>
            Pipeline stages
          </p>
          <div className="pipeline-strip" style={{ justifyContent: 'center' }}>
            {PIPELINE_STAGES.map((stage, i) => (
              <React.Fragment key={stage}>
                <span className="pipeline-badge">{stage}</span>
                {i < PIPELINE_STAGES.length - 1 && (
                  <span className="pipeline-badge__arrow">→</span>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}

function StatsBar() {
  const stats = [
    { value: '22', label: 'Pipeline Stages' },
    { value: '3×', label: 'Max Verifier Iterations' },
    { value: '100%', label: 'Claims Grounded' },
    { value: '3', label: 'Quality Presets' },
  ];
  return (
    <div style={{
      background: 'rgba(108,99,255,0.06)',
      borderTop: '1px solid rgba(108,99,255,0.15)',
      borderBottom: '1px solid rgba(108,99,255,0.15)',
      padding: '2rem 0',
    }}>
      <div className="container">
        <div className="row" style={{ justifyContent: 'center' }}>
          {stats.map(({ value, label }) => (
            <div key={label} className="col col--3" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--ifm-color-primary)', lineHeight: 1.1 }}>
                {value}
              </div>
              <div style={{ color: 'var(--ifm-color-emphasis-600)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                {label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const { siteConfig } = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <HeroBanner />
      <StatsBar />
      <main>
        <section className="features-section">
          <div className="container">
            <h2 style={{ textAlign: 'center', marginBottom: '0.5rem', fontSize: '2rem', fontWeight: 800 }}>
              What makes SlideSherlock different?
            </h2>
            <p style={{ textAlign: 'center', color: 'var(--ifm-color-emphasis-600)', marginBottom: '3rem', fontSize: '1.05rem' }}>
              Most video-generation tools hallucinate. SlideSherlock doesn't.
            </p>
            <div className="row">
              {FEATURES.map((props) => (
                <Feature key={props.title} {...props} />
              ))}
            </div>
          </div>
        </section>

        {/* Quick start teaser */}
        <section style={{ padding: '4rem 0', background: 'var(--ifm-background-surface-color)' }}>
          <div className="container" style={{ maxWidth: 760 }}>
            <h2 style={{ textAlign: 'center', marginBottom: '2rem', fontSize: '1.8rem', fontWeight: 800 }}>
              Up and running in minutes
            </h2>
            <div style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--ifm-color-emphasis-200)' }}>
              <div style={{ background: '#1e1e2e', padding: '1.2rem 1.5rem', fontFamily: 'monospace', fontSize: '0.88rem', lineHeight: 1.8, color: '#cdd6f4' }}>
                <div><span style={{ color: '#6c7086' }}># 1 — start infrastructure</span></div>
                <div><span style={{ color: '#89b4fa' }}>make</span> <span style={{ color: '#a6e3a1' }}>up</span></div>
                <div style={{ marginTop: '0.5rem' }}><span style={{ color: '#6c7086' }}># 2 — set up Python environment</span></div>
                <div><span style={{ color: '#89b4fa' }}>make</span> <span style={{ color: '#a6e3a1' }}>setup</span> <span style={{ color: '#89b4fa' }}>&amp;&amp; make</span> <span style={{ color: '#a6e3a1' }}>migrate</span></div>
                <div style={{ marginTop: '0.5rem' }}><span style={{ color: '#6c7086' }}># 3 — start API + worker (two terminals)</span></div>
                <div><span style={{ color: '#89b4fa' }}>make</span> <span style={{ color: '#a6e3a1' }}>api</span></div>
                <div><span style={{ color: '#89b4fa' }}>make</span> <span style={{ color: '#a6e3a1' }}>worker</span></div>
                <div style={{ marginTop: '0.5rem' }}><span style={{ color: '#6c7086' }}># 4 — submit a presentation</span></div>
                <div><span style={{ color: '#89b4fa' }}>curl</span> -X POST http://localhost:8000/jobs <span style={{ color: '#fab387' }}>-F</span> <span style={{ color: '#a6e3a1' }}>"file=@slides.pptx"</span></div>
              </div>
            </div>
            <div style={{ textAlign: 'center', marginTop: '2rem' }}>
              <Link className="button button--primary button--lg" to="/docs/getting-started/prerequisites">
                Full Installation Guide →
              </Link>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
