/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  mainSidebar: [
    {
      type: 'doc',
      id: 'intro',
      label: '🎬 Introduction',
    },
    {
      type: 'category',
      label: '🚀 Getting Started',
      collapsed: false,
      items: [
        'getting-started/prerequisites',
        'getting-started/installation',
        'getting-started/quickstart',
      ],
    },
    {
      type: 'category',
      label: '🏗️ Architecture',
      collapsed: false,
      items: [
        'architecture/overview',
        'architecture/pipeline-stages',
        'architecture/evidence-system',
        'architecture/graph-system',
        'architecture/providers',
      ],
    },
    {
      type: 'category',
      label: '⚙️ Configuration',
      items: [
        'configuration/environment-variables',
        'configuration/quality-presets',
      ],
    },
    {
      type: 'category',
      label: '📖 Guides',
      items: [
        'guides/infrastructure',
        'guides/api-server',
        'guides/worker',
        'guides/submitting-jobs',
      ],
    },
    {
      type: 'category',
      label: '🔌 API Reference',
      items: [
        'api-reference/rest-api',
      ],
    },
    {
      type: 'category',
      label: '🧪 Testing',
      items: [
        'testing/unit-tests',
        'testing/e2e-tests',
      ],
    },
    {
      type: 'category',
      label: '🔧 Troubleshooting',
      items: [
        'troubleshooting/common-issues',
      ],
    },
  ],
};

module.exports = sidebars;
