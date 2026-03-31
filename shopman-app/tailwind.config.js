/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './channels/web/templates/**/*.html',
    './shop/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        background: 'oklch(var(--background) / <alpha-value>)',
        foreground: 'oklch(var(--foreground) / <alpha-value>)',
        surface: {
          DEFAULT: 'oklch(var(--surface) / <alpha-value>)',
          hover: 'oklch(var(--surface-hover) / <alpha-value>)',
        },
        input: 'oklch(var(--input) / <alpha-value>)',
        muted: {
          DEFAULT: 'oklch(var(--muted) / <alpha-value>)',
          foreground: 'oklch(var(--foreground-muted) / <alpha-value>)',
        },
        border: 'oklch(var(--border) / <alpha-value>)',
        ring: 'oklch(var(--ring) / <alpha-value>)',
        primary: {
          DEFAULT: 'oklch(var(--primary) / <alpha-value>)',
          hover: 'oklch(var(--primary-hover) / <alpha-value>)',
          foreground: 'oklch(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'oklch(var(--secondary) / <alpha-value>)',
          hover: 'oklch(var(--secondary-hover) / <alpha-value>)',
          foreground: 'oklch(var(--secondary-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'oklch(var(--accent) / <alpha-value>)',
          hover: 'oklch(var(--accent-hover) / <alpha-value>)',
          foreground: 'oklch(var(--accent-foreground) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'oklch(var(--success) / <alpha-value>)',
          light: 'oklch(var(--success-light) / <alpha-value>)',
          foreground: 'oklch(var(--success-foreground) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'oklch(var(--warning) / <alpha-value>)',
          light: 'oklch(var(--warning-light) / <alpha-value>)',
          foreground: 'oklch(var(--warning-foreground) / <alpha-value>)',
        },
        error: {
          DEFAULT: 'oklch(var(--error) / <alpha-value>)',
          light: 'oklch(var(--error-light) / <alpha-value>)',
          foreground: 'oklch(var(--error-foreground) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'oklch(var(--info) / <alpha-value>)',
          light: 'oklch(var(--info-light) / <alpha-value>)',
          foreground: 'oklch(var(--info-foreground) / <alpha-value>)',
        },
      },
      fontFamily: {
        heading: ['var(--font-heading)'],
        body: ['var(--font-body)'],
      },
      fontSize: {
        'display':  ['var(--text-display)',  { lineHeight: 'var(--leading-display)',  letterSpacing: 'var(--tracking-display)',  fontWeight: '700' }],
        'h1':       ['var(--text-h1)',       { lineHeight: 'var(--leading-h1)',       letterSpacing: 'var(--tracking-h1)',       fontWeight: '700' }],
        'h2':       ['var(--text-h2)',       { lineHeight: 'var(--leading-h2)',       letterSpacing: 'var(--tracking-h2)',       fontWeight: '700' }],
        'h3':       ['var(--text-h3)',       { lineHeight: 'var(--leading-h3)',       letterSpacing: 'var(--tracking-h3)',       fontWeight: '600' }],
        'h4':       ['var(--text-h4)',       { lineHeight: 'var(--leading-h4)',       letterSpacing: 'var(--tracking-h4)',       fontWeight: '600' }],
        'body-lg':  ['var(--text-body-lg)',  { lineHeight: 'var(--leading-body-lg)' }],
        'body':     ['var(--text-body)',     { lineHeight: 'var(--leading-body)' }],
        'body-sm':  ['var(--text-body-sm)', { lineHeight: 'var(--leading-body-sm)' }],
        'caption':  ['var(--text-caption)',  { lineHeight: 'var(--leading-caption)',  letterSpacing: 'var(--tracking-caption)' }],
        'overline': ['var(--text-overline)', { lineHeight: 'var(--leading-overline)', letterSpacing: 'var(--tracking-overline)', fontWeight: '600', textTransform: 'uppercase' }],
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },
      screens: {
        'xs': '375px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
