/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#090d16',
        surface: '#0f172a',
        'surface-elevated': '#1e293b',
        'surface-hover': '#334155',
        border: '#1e293b',
        'border-focus': '#38bdf8',
        'severity-critical': '#ef4444',
        'severity-high': '#f97316',
        'severity-medium': '#eab308',
        'severity-low': '#3b82f6',
        'status-healthy': '#10b981',
        'status-unknown': '#64748b',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
