export default defineAppConfig({
  ui: {
    colors: {
      primary: 'amber',
      neutral: 'stone'
    },
    button: {
      slots: {
        base: 'font-semibold'
      },
      defaultVariants: {
        color: 'primary'
      }
    },
    card: {
      slots: {
        root: 'rounded-lg',
        header: 'p-4 sm:p-5',
        body: 'p-4 sm:p-5',
        footer: 'p-4 sm:p-5'
      }
    }
  }
})
