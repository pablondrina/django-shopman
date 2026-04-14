/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './shopman/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        /* Tokens = canais R G B (0–255) em _design_tokens — sem OKLCH no runtime */
        background: 'rgb(var(--background) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--surface) / <alpha-value>)',
          hover: 'rgb(var(--surface-hover) / <alpha-value>)',
        },
        card: {
          DEFAULT: 'rgb(var(--card) / <alpha-value>)',
          foreground: 'rgb(var(--card-foreground) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'rgb(var(--popover) / <alpha-value>)',
          foreground: 'rgb(var(--popover-foreground) / <alpha-value>)',
        },
        input: 'rgb(var(--input) / <alpha-value>)',
        muted: {
          DEFAULT: 'rgb(var(--muted) / <alpha-value>)',
          foreground: 'rgb(var(--muted-foreground) / <alpha-value>)',
        },
        border: 'rgb(var(--border) / <alpha-value>)',
        ring: 'rgb(var(--ring) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--primary) / <alpha-value>)',
          hover: 'rgb(var(--primary-hover) / <alpha-value>)',
          foreground: 'rgb(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary) / <alpha-value>)',
          hover: 'rgb(var(--secondary-hover) / <alpha-value>)',
          foreground: 'rgb(var(--secondary-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          hover: 'rgb(var(--accent-hover) / <alpha-value>)',
          foreground: 'rgb(var(--accent-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'rgb(var(--destructive) / <alpha-value>)',
          foreground: 'rgb(var(--destructive-foreground) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--success) / <alpha-value>)',
          light: 'var(--success-light)',
          foreground: 'rgb(var(--success-foreground) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--warning) / <alpha-value>)',
          light: 'var(--warning-light)',
          foreground: 'rgb(var(--warning-foreground) / <alpha-value>)',
        },
        error: {
          DEFAULT: 'rgb(var(--error) / <alpha-value>)',
          light: 'var(--error-light)',
          foreground: 'rgb(var(--error-foreground) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--info) / <alpha-value>)',
          light: 'var(--info-light)',
          foreground: 'rgb(var(--info-foreground) / <alpha-value>)',
        },
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
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
