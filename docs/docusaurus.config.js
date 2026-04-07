// @ts-check
const { themes } = require('prism-react-renderer');
const lightTheme = themes.github;
const darkTheme = themes.dracula;

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'SlideSherlock',
  tagline: 'Transform any presentation into a grounded, narrated explainer video — hallucination-free.',
  favicon: 'img/favicon.ico',

  // GitHub Pages serves at https://sachinkg12.github.io/SlideSherlock/
  // Override URL/baseUrl with env vars when deploying to a custom domain
  url: process.env.DOCS_URL || 'https://sachinkg12.github.io',
  baseUrl: process.env.DOCS_BASE_URL || '/SlideSherlock/',
  organizationName: 'sachinkg12',
  projectName: 'SlideSherlock',
  trailingSlash: false,

  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  markdown: {
    mermaid: true,
  },

  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: 'content',
          routeBasePath: 'docs',
          sidebarPath: require.resolve('./sidebars.js'),
          showLastUpdateTime: true,
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      image: 'img/og-card.png',
      colorMode: {
        defaultMode: 'dark',
        disableSwitch: false,
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: 'SlideSherlock',
        logo: {
          alt: 'SlideSherlock Logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'mainSidebar',
            position: 'left',
            label: 'Documentation',
          },
          {
            to: '/docs/api-reference/rest-api',
            label: 'API Reference',
            position: 'left',
          },
          {
            href: 'https://github.com/sachinkg12/SlideSherlock',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Get Started',
            items: [
              { label: 'Prerequisites', to: '/docs/getting-started/prerequisites' },
              { label: 'Installation', to: '/docs/getting-started/installation' },
              { label: 'Quick Start', to: '/docs/getting-started/quickstart' },
            ],
          },
          {
            title: 'Architecture',
            items: [
              { label: 'Overview', to: '/docs/architecture/overview' },
              { label: 'Pipeline Stages', to: '/docs/architecture/pipeline-stages' },
              { label: 'Evidence System', to: '/docs/architecture/evidence-system' },
            ],
          },
          {
            title: 'Reference',
            items: [
              { label: 'REST API', to: '/docs/api-reference/rest-api' },
              { label: 'Configuration', to: '/docs/configuration/environment-variables' },
              { label: 'Quality Presets', to: '/docs/configuration/quality-presets' },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} SlideSherlock. Built with Docusaurus.`,
      },
      prism: {
        theme: lightTheme,
        darkTheme: darkTheme,
        additionalLanguages: ['bash', 'python', 'json', 'yaml', 'docker'],
      },
      mermaid: {
        theme: { light: 'neutral', dark: 'dark' },
        options: {
          maxTextSize: 50000,
        },
      },
      algolia: undefined,
    }),
};

module.exports = config;
