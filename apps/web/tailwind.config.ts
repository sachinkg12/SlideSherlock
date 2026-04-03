import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: 'rgba(255,255,255,0.03)',
        'surface-hover': 'rgba(255,255,255,0.06)',
        'border-subtle': 'rgba(255,255,255,0.08)',
        'border-active': 'rgba(255,255,255,0.15)',
        'text-primary': '#f0f0f5',
        'text-secondary': '#6b7280',
        dark: '#0a0a0f',
        'dark-raised': '#12121a',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          "'Segoe UI'",
          'Roboto',
          'Oxygen',
          'Ubuntu',
          'Cantarell',
          "'Fira Sans'",
          "'Droid Sans'",
          "'Helvetica Neue'",
          'sans-serif',
        ],
      },
      animation: {
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'border-rotate': 'border-rotate 4s linear infinite',
        'fade-in-up': 'fade-in-up 0.5s ease-out',
        'shake': 'shake 0.5s ease-in-out',
        'confetti': 'confetti 1.5s ease-out forwards',
      },
      keyframes: {
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(99, 102, 241, 0.2)' },
          '50%': { boxShadow: '0 0 40px rgba(99, 102, 241, 0.4)' },
        },
        'border-rotate': {
          '0%': { '--angle': '0deg' },
          '100%': { '--angle': '360deg' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'shake': {
          '0%, 100%': { transform: 'translateX(0)' },
          '20%': { transform: 'translateX(-8px)' },
          '40%': { transform: 'translateX(8px)' },
          '60%': { transform: 'translateX(-4px)' },
          '80%': { transform: 'translateX(4px)' },
        },
        'confetti': {
          '0%': { transform: 'translateY(0) rotate(0deg)', opacity: '1' },
          '100%': { transform: 'translateY(-200px) rotate(720deg)', opacity: '0' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
